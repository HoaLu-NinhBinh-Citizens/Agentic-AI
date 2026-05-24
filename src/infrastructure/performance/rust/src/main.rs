use clap::Parser;
use sha2::{Digest, Sha256};
use std::collections::HashMap;
use std::fs;
use std::io::{BufRead, BufReader, Read, Write};
use std::path::Path;
use walkdir::WalkDir;

#[derive(Parser)]
#[command(name = "ai-support-perf")]
#[command(about = "High-performance CLI utilities for Agentic-AI")]
struct Cli {
    #[command(subcommand)]
    command: Commands,
}

#[derive(clap::Subcommand)]
enum Commands {
    /// Fast file globbing
    Glob {
        root: String,
        pattern: String,
        #[arg(long, default_value_t = 10)]
        max_depth: usize,
    },
    
    /// Compute file hash
    HashFile {
        /// Path to file
        path: String,
        /// Hash algorithm
        #[arg(long, default_value = "sha256")]
        algorithm: String,
    },
    
    /// Fast grep
    Grep {
        /// Root directory
        #[arg(long)]
        root: String,
        /// Search pattern
        #[arg(long)]
        pattern: String,
        /// Output JSON
        #[arg(long)]
        json: bool,
        /// Case sensitive
        #[arg(long)]
        case_sensitive: bool,
        /// Context lines
        #[arg(long, default_value_t = 0)]
        context: usize,
    },
    
    /// Copy directory tree
    CopyTree {
        source: String,
        destination: String,
    },
    
    /// Find duplicate files
    FindDupes {
        root: String,
    },
    
    /// Stream JSON objects
    JsonStream,
    
    /// Hash directory for change detection
    HashDir {
        root: String,
    },
}

fn main() -> anyhow::Result<()> {
    let cli = Cli::parse();

    match cli.command {
        Commands::Glob { root, pattern, max_depth } => {
            let mut files = Vec::new();
            
            for entry in WalkDir::new(&root)
                .max_depth(max_depth)
                .into_iter()
                .filter_map(|e| e.ok())
            {
                let path = entry.path();
                if let Some(name) = path.file_name() {
                    if glob_match(&name.to_string_lossy(), &pattern) {
                        files.push(path.to_string_lossy().to_string());
                    }
                }
            }
            
            files.sort();
            for f in files {
                println!("{}", f);
            }
        }
        
        Commands::HashFile { path, algorithm } => {
            let mut file = fs::File::open(&path)?;
            let mut hasher = match algorithm.as_str() {
                "sha256" => Box::new(Sha256::new()) as Box<dyn std::hash::Hasher>,
                _ => Box::new(Sha256::new()),
            };
            
            let mut buffer = [0u8; 8192];
            loop {
                let bytes_read = file.read(&mut buffer)?;
                if bytes_read == 0 {
                    break;
                }
                hasher.update(&buffer[..bytes_read]);
            }
            
            println!("{:x}", hasher.finish());
        }
        
        Commands::Grep {
            root,
            pattern,
            json,
            case_sensitive,
            context,
        } => {
            let pattern = if case_sensitive {
                regex::Regex::new(&pattern)?
            } else {
                regex::Regex::new(&format!("(?i){}", pattern))?
            };
            
            let mut results: Vec<String> = Vec::new();
            
            for entry in WalkDir::new(&root)
                .into_iter()
                .filter_map(|e| e.ok())
            {
                let path = entry.path();
                if !path.is_file() {
                    continue;
                }
                
                // Skip binary files
                if let Some(ext) = path.extension() {
                    let ext = ext.to_string_lossy().to_lowercase();
                    if matches!(ext.as_str(), "png" | "jpg" | "jpeg" | "gif" | "zip" | "tar" | "gz") {
                        continue;
                    }
                }
                
                if let Ok(file) = fs::File::open(path) {
                    let reader = BufReader::new(file);
                    
                    for (line_num, line_result) in reader.lines().enumerate() {
                        if let Ok(line) = line_result {
                            if pattern.is_match(&line) {
                                if json {
                                    let escaped_pattern = pattern.to_string();
                                    println!(
                                        r#"{{"path":"{}","line_number":{},"line":"{}"}}"#,
                                        path.to_string_lossy(),
                                        line_num + 1,
                                        line.replace('"', "\\\"")
                                    );
                                } else {
                                    println!("{}:{}:{}", path.to_string_lossy(), line_num + 1, line);
                                }
                            }
                        }
                    }
                }
            }
        }
        
        Commands::CopyTree { source, destination } => {
            let source_path = Path::new(&source);
            let dest_path = Path::new(&destination);
            
            fs::create_dir_all(dest_path)?;
            
            for entry in WalkDir::new(source_path)
                .into_iter()
                .filter_map(|e| e.ok())
            {
                let src = entry.path();
                let dst = dest_path.join(src.strip_prefix(source_path).unwrap());
                
                if src.is_dir() {
                    fs::create_dir_all(&dst)?;
                } else {
                    if let Some(parent) = dst.parent() {
                        fs::create_dir_all(parent)?;
                    }
                    fs::copy(src, &dst)?;
                }
            }
            
            println!("Copied {} to {}", source, destination);
        }
        
        Commands::FindDupes { root } => {
            let mut size_map: HashMap<u64, Vec<String>> = HashMap::new();
            
            // Group by size
            for entry in WalkDir::new(&root)
                .into_iter()
                .filter_map(|e| e.ok())
            {
                let path = entry.path();
                if path.is_file() {
                    if let Ok(metadata) = fs::metadata(path) {
                        let size = metadata.len();
                        size_map
                            .entry(size)
                            .or_default()
                            .push(path.to_string_lossy().to_string());
                    }
                }
            }
            
            // Hash files with same size
            let mut hash_map: HashMap<String, Vec<String>> = HashMap::new();
            
            for (_, paths) in size_map {
                if paths.len() < 2 {
                    continue;
                }
                
                for path in paths {
                    let mut file = fs::File::open(&path)?;
                    let mut hasher = Sha256::new();
                    let mut buffer = [0u8; 8192];
                    
                    loop {
                        let bytes_read = file.read(&mut buffer)?;
                        if bytes_read == 0 {
                            break;
                        }
                        hasher.update(&buffer[..bytes_read]);
                    }
                    
                    let hash = format!("{:x}", hasher.finish());
                    hash_map.entry(hash).or_default().push(path);
                }
            }
            
            // Output duplicate groups
            for (_, paths) in hash_map {
                if paths.len() > 1 {
                    println!("{}", paths.join("\t"));
                }
            }
        }
        
        Commands::JsonStream => {
            let stdin = std::io::stdin();
            let mut reader = stdin.lock();
            let mut buffer = String::new();
            
            while reader.read_line(&mut buffer)? > 0 {
                if let Ok(json) = serde_json::from_str::<serde_json::Value>(&buffer) {
                    println!("{}", serde_json::to_string(&json)?);
                }
                buffer.clear();
            }
        }
        
        Commands::HashDir { root } => {
            let mut hashes: HashMap<String, String> = HashMap::new();
            
            let mut entries: Vec<_> = WalkDir::new(&root)
                .into_iter()
                .filter_map(|e| e.ok())
                .filter(|e| e.path().is_file())
                .collect();
            
            entries.sort_by_key(|e| e.path());
            
            for entry in entries {
                let path = entry.path();
                let rel_path = path.strip_prefix(&root)
                    .unwrap_or(path)
                    .to_string_lossy()
                    .to_string();
                
                if let Ok(file) = fs::File::open(path) {
                    let mut hasher = Sha256::new();
                    let mut reader = BufReader::new(file);
                    let mut buffer = [0u8; 8192];
                    
                    loop {
                        let bytes_read = reader.read(&mut buffer)?;
                        if bytes_read == 0 {
                            break;
                        }
                        hasher.update(&buffer[..bytes_read]);
                    }
                    
                    let hash = format!("{:x}", hasher.finish());
                    hashes.insert(rel_path, hash);
                }
            }
            
            println!("{}", serde_json::to_string(&hashes)?);
        }
    }

    Ok(())
}

fn glob_match(name: &str, pattern: &str) -> bool {
    let parts: Vec<&str> = pattern.split('/').collect();
    let name_parts: Vec<&str> = name.split('/').collect();

    fn matches_parts(name_parts: &[&str], pattern_parts: &[&str]) -> bool {
        match (name_parts, pattern_parts) {
            ([], []) => true,
            ([], [p]) => p.is_empty(),
            ([n, rest @ ..], [p, prest @ ..]) => {
                if p == "*" {
                    !n.contains('/') && matches_parts(rest, prest)
                } else if p == "**" {
                    matches_parts(name_parts, prest)
                        || matches_parts(rest, pattern_parts)
                        || matches_parts(rest, prest)
                } else if n == p {
                    matches_parts(rest, prest)
                } else {
                    false
                }
            }
            _ => false,
        }
    }

    matches_parts(&name_parts, &parts)
}
