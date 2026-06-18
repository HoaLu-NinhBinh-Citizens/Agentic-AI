//! Language detection and tree-sitter query definitions.
//!
//! Each supported language provides its grammar plus two queries: one that
//! captures symbol *definitions* (with a kind) and one that captures *call
//! references* (the call sites Next Edit Prediction walks). Adding a language
//! means adding a grammar dep and an arm here — nothing downstream changes.

use tree_sitter::Language;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Lang {
    Rust,
    Python,
    C,
    Cpp,
}

impl Lang {
    /// Map a workspace-relative path to a language by extension. `None` means
    /// "don't build a symbol graph for this file" (still indexed by Merkle).
    pub fn from_path(path: &str) -> Option<Lang> {
        let ext = path.rsplit('.').next()?;
        match ext {
            "rs" => Some(Lang::Rust),
            "py" | "pyi" => Some(Lang::Python),
            // `.h` defaults to C (firmware); C++ headers use .hpp/.hh/.hxx.
            "c" | "h" => Some(Lang::C),
            "cpp" | "cc" | "cxx" | "c++" | "hpp" | "hh" | "hxx" => Some(Lang::Cpp),
            _ => None,
        }
    }

    pub fn name(self) -> &'static str {
        match self {
            Lang::Rust => "rust",
            Lang::Python => "python",
            Lang::C => "c",
            Lang::Cpp => "cpp",
        }
    }

    pub fn ts_language(self) -> Language {
        match self {
            Lang::Rust => tree_sitter_rust::LANGUAGE.into(),
            Lang::Python => tree_sitter_python::LANGUAGE.into(),
            Lang::C => tree_sitter_c::LANGUAGE.into(),
            Lang::Cpp => tree_sitter_cpp::LANGUAGE.into(),
        }
    }

    /// Query whose captures are `@name` (the identifier) inside a `@def.<kind>`
    /// container. The container capture's range spans the whole definition; the
    /// `@name` capture gives the symbol name.
    pub fn defs_query(self) -> &'static str {
        match self {
            Lang::Rust => {
                r#"
                (function_item name: (identifier) @name) @def.function
                (struct_item name: (type_identifier) @name) @def.struct
                (enum_item name: (type_identifier) @name) @def.enum
                (trait_item name: (type_identifier) @name) @def.trait
                (const_item name: (identifier) @name) @def.const
                (static_item name: (identifier) @name) @def.static
                "#
            }
            Lang::Python => {
                r#"
                (function_definition name: (identifier) @name) @def.function
                (class_definition name: (identifier) @name) @def.class
                "#
            }
            Lang::C => {
                r#"
                (function_definition declarator: (function_declarator declarator: (identifier) @name)) @def.function
                (function_definition declarator: (pointer_declarator declarator: (function_declarator declarator: (identifier) @name))) @def.function
                (struct_specifier name: (type_identifier) @name) @def.struct
                (enum_specifier name: (type_identifier) @name) @def.enum
                (union_specifier name: (type_identifier) @name) @def.union
                (type_definition declarator: (type_identifier) @name) @def.typedef
                "#
            }
            Lang::Cpp => {
                r#"
                (function_definition declarator: (function_declarator declarator: (identifier) @name)) @def.function
                (function_definition declarator: (function_declarator declarator: (field_identifier) @name)) @def.method
                (function_definition declarator: (function_declarator declarator: (qualified_identifier) @name)) @def.function
                (function_definition declarator: (pointer_declarator declarator: (function_declarator declarator: (identifier) @name))) @def.function
                (struct_specifier name: (type_identifier) @name) @def.struct
                (class_specifier name: (type_identifier) @name) @def.class
                (enum_specifier name: (type_identifier) @name) @def.enum
                (namespace_definition name: (namespace_identifier) @name) @def.namespace
                (type_definition declarator: (type_identifier) @name) @def.typedef
                "#
            }
        }
    }

    /// Query whose `@ref.call` capture is the callee name at a call site.
    pub fn refs_query(self) -> &'static str {
        match self {
            Lang::Rust => {
                r#"
                (call_expression function: (identifier) @ref.call)
                (call_expression function: (field_expression field: (field_identifier) @ref.call))
                (call_expression function: (scoped_identifier name: (identifier) @ref.call))
                (macro_invocation macro: (identifier) @ref.call)
                "#
            }
            Lang::Python => {
                r#"
                (call function: (identifier) @ref.call)
                (call function: (attribute attribute: (identifier) @ref.call))
                "#
            }
            Lang::C => {
                r#"
                (call_expression function: (identifier) @ref.call)
                (call_expression function: (field_expression field: (field_identifier) @ref.call))
                "#
            }
            Lang::Cpp => {
                r#"
                (call_expression function: (identifier) @ref.call)
                (call_expression function: (field_expression field: (field_identifier) @ref.call))
                (call_expression function: (qualified_identifier name: (identifier) @ref.call))
                "#
            }
        }
    }
}
