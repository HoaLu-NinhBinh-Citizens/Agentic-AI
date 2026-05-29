#!/usr/bin/env python3
"""
NXP RTD AUTOSAR Plugin to Markdown Converter
============================================
A robust tool to convert Eclipse plugin configurations and source code
into comprehensive Markdown documentation.

Features:
- Parse plugin.xml with proper namespace handling
- Parse C/H files using pycparser for accurate AST extraction
- Extract documentation links and copy PDF files
- Generate structured Markdown with API references
- Support incremental updates

Usage:
    python convert_plugins_to_markdown.py <plugins_dir> [-o output_dir]
    python convert_plugins_to_markdown.py . -o docs --single Dio_TS_T40D34M30I0R0
"""

import os
import sys
import re
import json
import shutil
import hashlib
import argparse
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any, Set, Tuple
from dataclasses import dataclass, field, asdict
from abc import ABC, abstractmethod
from functools import lru_cache
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(name)s:%(lineno)d] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


# ============================================================================
# COMPILED REGEX PATTERNS (for performance)
# ============================================================================

# XML comment removal
RE_XML_COMMENT = re.compile(r'<!--.*?-->', re.DOTALL)

# C-style comment removal
RE_C_MULTILINE_COMMENT = re.compile(r'/\*.*?\*/', re.DOTALL)
RE_C_SINGLELINE_COMMENT = re.compile(r'//.*?$', re.MULTILINE)

# Doxygen comment blocks
RE_DOXYGEN_BLOCK = re.compile(r'/\*\*\s*\n((?:[ \t]+\*[^\n]*\n)+)[ \t]*\*/')
RE_DOXYGEN_SINGLELINE = re.compile(r'(?:///|//!)\s*([^\n]*\n){1,3}')

# Header patterns
RE_INCLUDE = re.compile(r'#include\s*[<"]([^>"]+)[>"]')
RE_DEFINE = re.compile(r'#define\s+(\w+)\s+')
RE_FUNC_LIKE_MACRO = re.compile(r'#define\s+(\w+)\s+\([^)]+\)')

# Function patterns - expanded AUTOSAR types
RE_FUNC_RETURN_TYPES = (
    r'Std_ReturnType|void|uint8|uint16|uint32|uint64|'
    r'int8|int16|int32|int64|boolean|'
    r'Dio_|Can_|CanIf_|CanSM_|CanTrcv_|'
    r'Mcu_|Port_|Gpt_|Icu_|Ocu_|'
    r'Spi_|I2c_|I2c_|Uart_|Lpuart_|'
    r'Pwm_|Rtc_|Wdg_|Eth_|EthIf_|'
    r'Lin_|LinIf_|Fee_|Ea_|'
    r'SchM_|Mcal_|Platform_|'
    r'[A-Z][A-Za-z0-9_]*Type|[A-Z][A-Za-z0-9_]*Ptr'
)

# Callback/function pointer typedef
RE_CALLBACK_TYPEDEF = re.compile(
    r'typedef\s+(?:void\s+|[\w\s\*]+)\(\s*\*(\w+)\s*\)\s*\([^)]*\)\s*;',
    re.DOTALL
)

# Version patterns
RE_VERSION_MACRO = re.compile(r'#define\s+(\w+_VERSION)\s+(\d+)')
RE_VENDOR_ID = re.compile(r'#define\s+(\w+_VENDOR_ID)\s+(\d+)')
RE_MODULE_ID = re.compile(r'#define\s+(\w+_MODULE_ID)\s+(\d+)')

# XML namespace detection
RE_XML_NAMESPACE = re.compile(r'xmlns(?::(\w+))?=["\']([^"\']+)["\']')

# Manifest header
RE_MANIFEST_HEADER = re.compile(r'<!--\s*\n(.*?)\n-->', re.DOTALL)


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class VersionInfo:
    """Version information container."""
    vendor_id: str = ""
    module_id: str = ""
    ar_major: str = ""
    ar_minor: str = ""
    ar_patch: str = ""
    sw_major: str = ""
    sw_minor: str = ""
    sw_patch: str = ""
    
    def __str__(self) -> str:
        parts = []
        if self.sw_major:
            parts.append(f"{self.sw_major}.{self.sw_minor}.{self.sw_patch}")
        if self.ar_major:
            parts.append(f"AUTOSAR {self.ar_major}.{self.ar_minor}.{self.ar_patch}")
        return " ".join(parts) if parts else "N/A"


@dataclass
class ApiFunction:
    """API function definition."""
    name: str
    return_type: str
    params: List[Tuple[str, str]] = field(default_factory=list)
    brief: str = ""
    description: str = ""
    preconditions: str = ""
    postconditions: str = ""
    return_desc: str = ""
    errors: List[str] = field(default_factory=list)
    is_public: bool = True


@dataclass
class ErrorCode:
    """Error code definition."""
    name: str
    value: str
    description: str


@dataclass
class SourceFile:
    """Source file information."""
    path: Path
    filename: str
    version: VersionInfo = field(default_factory=VersionInfo)
    functions: List[ApiFunction] = field(default_factory=list)
    local_functions: List[str] = field(default_factory=list)
    macros: List[Tuple[str, str]] = field(default_factory=list)
    includes: List[str] = field(default_factory=list)
    doc: str = ""


@dataclass
class HeaderFile:
    """Header file information."""
    path: Path
    filename: str
    version: VersionInfo = field(default_factory=VersionInfo)
    public_functions: List[ApiFunction] = field(default_factory=list)
    error_codes: List[ErrorCode] = field(default_factory=list)
    api_ids: List[Tuple[str, str]] = field(default_factory=list)
    macros: List[Tuple[str, str]] = field(default_factory=list)  # (name, value)
    includes: List[str] = field(default_factory=list)
    # Struct/enum/typedef definitions
    structs: List[Tuple[str, str]] = field(default_factory=list)  # (name, fields_summary)
    enums: List[Tuple[str, str]] = field(default_factory=list)  # (name, values_summary)
    typedefs: List[Tuple[str, str]] = field(default_factory=list)  # (alias, original_type)
    doc: str = ""


@dataclass
class PluginExtension:
    """Plugin extension information."""
    point: str
    id: str
    name: str
    module_id: str = ""
    generator_class: str = ""
    modes: str = ""
    parameters: Dict[str, str] = field(default_factory=dict)
    schema_resource: str = ""
    schema_type: str = ""
    toc_file: str = ""


@dataclass
class PluginInfo:
    """Complete plugin information."""
    name: str
    path: Path
    
    # Metadata from plugin.xml header
    file_version: str = ""
    brief: str = ""
    project: str = ""
    platform: str = ""
    peripheral: str = ""
    dependencies: List[str] = field(default_factory=list)  # From MANIFEST.MF Require-Bundle
    bundle_version: str = ""  # From MANIFEST.MF
    bundle_vendor: str = ""  # From MANIFEST.MF
    autosar_version: str = ""
    sw_version: str = ""
    build_version: str = ""
    copyright: str = ""
    
    # Module configuration
    module_id: str = ""
    module_label: str = ""
    description: str = ""
    category_type: str = ""
    category_layer: str = ""
    category_category: str = ""
    category_component: str = ""
    target: str = ""
    derivate: str = ""
    spec_version: str = ""
    rel_version: str = ""
    
    # Documentation links
    doc_links: List[Dict[str, str]] = field(default_factory=list)
    
    # Extensions
    extensions: List[PluginExtension] = field(default_factory=list)
    
    # Build info
    build_targets: List[str] = field(default_factory=list)
    
    # XDM configuration files (Tresos)
    xdm_configs: List[Dict[str, Any]] = field(default_factory=list)
    
    # Source code
    source_files: List[SourceFile] = field(default_factory=list)
    header_files: List[HeaderFile] = field(default_factory=list)
    
    # Computed properties
    @property
    def version_str(self) -> str:
        return self.sw_version or "N/A"
    
    @property
    def api_count(self) -> int:
        return sum(len(h.public_functions) for h in self.header_files)


# ============================================================================
# XML PARSER
# ============================================================================

class XmlNamespace:
    """Handle XML namespaces properly."""
    
    # Common namespaces in Eclipse/Tresos plugins
    COMMON_NAMESPACES = {
        'ns': 'http://schemas.xmlsoap.org/wsdl/',
        'eco': 'http://www.eclipse.org/uml2/2.0.0/Core',
        'extension': 'http://schemas.osgi.org/cmi/1.0.0',
    }
    
    @classmethod
    def register_namespaces(cls, root, additional_ns: Dict[str, str] = None) -> None:
        """Register all namespaces found in the document."""
        namespaces = dict(cls.COMMON_NAMESPACES)
        if additional_ns:
            namespaces.update(additional_ns)
        
        for prefix, uri in namespaces.items():
            try:
                root.register_namespace(prefix, uri)
            except AttributeError:
                pass  # ElementTree doesn't need explicit registration


class PluginXmlParser:
    """Parse plugin.xml with proper namespace handling."""
    
    def __init__(self, plugin_path: Path):
        self.plugin_path = plugin_path
        self.plugin_xml_path = plugin_path / "plugin.xml"
        self._xml_content: Optional[str] = None
        self._root: Optional[Any] = None
        self._namespaces: Dict[str, str] = {}
    
    def _detect_namespaces(self, content: str) -> None:
        """Detect namespaces from XML content."""
        ns_pattern = r'xmlns(?::(\w+))?=["\']([^"\']+)["\']'
        for match in re.finditer(ns_pattern, content):
            prefix = match.group(1) or 'default'
            uri = match.group(2)
            self._namespaces[prefix] = uri
    
    def _parse_namespaces(self) -> str:
        """Build namespace mapping string for ElementPath."""
        # For ElementTree, we need to register namespaces
        return ""
    
    def parse(self) -> PluginInfo:
        """Parse plugin.xml and return PluginInfo."""
        plugin_info = PluginInfo(
            name=self.plugin_path.name,
            path=self.plugin_path
        )
        
        if not self.plugin_xml_path.exists():
            logger.warning(f"plugin.xml not found in {self.plugin_path}")
            return plugin_info
        
        try:
            self._xml_content = self.plugin_xml_path.read_text(encoding='utf-8')
            self._detect_namespaces(self._xml_content)
            
            # Remove comments before parsing
            clean_content = RE_XML_COMMENT.sub('', self._xml_content)
            
            self._root = ET.fromstring(clean_content)
            
            # Extract header info
            self._extract_header_info(plugin_info)
            
            # Extract extensions
            self._extract_extensions(plugin_info)
            
            # Extract MANIFEST.MF info for dependencies
            manifest = ManifestParser(self.plugin_path).parse()
            plugin_info.bundle_version = manifest.get('bundle_version', '')
            plugin_info.bundle_vendor = manifest.get('bundle_vendor', '')
            plugin_info.dependencies = manifest.get('dependencies', [])
            
        except ET.ParseError as e:
            logger.error(f"XML Parse error in {self.plugin_xml_path}: {e}")
        except Exception as e:
            logger.error(f"Error parsing plugin.xml: {e}")
        
        return plugin_info
    
    def _extract_header_info(self, plugin_info: PluginInfo) -> None:
        """Extract project header information from comment block."""
        if not self._xml_content:
            return
        
        # Match the header comment block
        header_match = re.search(
            r'<!--\s*\n(.*?)\n-->',
            self._xml_content,
            re.DOTALL
        )
        
        if not header_match:
            return
        
        header = header_match.group(1)
        
        patterns = {
            'project': r'Project\s*:\s*([^\n]+)',
            'platform': r'Platform\s*:\s*([^\n]+)',
            'peripheral': r'Peripheral\s*:\s*([^\n]+)',
            'dependencies': r'Dependencies\s*:\s*([^\n]+)',
            'autosar_version': r'Autosar Version\s*:\s*([^\n]+)',
            'sw_version': r'SW Version\s*:\s*([^\n]+)',
            'build_version': r'Build Version\s*:\s*([^\n]+)',
            'copyright': r'Copyright\s+([^\n]+)',
        }
        
        for key, pattern in patterns.items():
            match = re.search(pattern, header)
            if match:
                setattr(plugin_info, key, match.group(1).strip())
    
    def _extract_extensions(self, plugin_info: PluginInfo) -> None:
        """Extract extension information from plugin.xml."""
        if not self._root:
            return
        
        # Try lxml first for better namespace handling if available
        extensions = None
        if HAS_LXML:
            try:
                root_lxml = lxml_ET.fromstring(self._xml_content.encode('utf-8'))
                # Find all extension elements regardless of namespace
                extensions = root_lxml.xpath('.//extension')
                logger.debug(f"Found {len(extensions)} extensions using lxml in {plugin_info.name}")
            except Exception as e:
                logger.debug(f"lxml parsing failed for {plugin_info.name}: {e}")
        
        # Fallback to direct search (works for non-namespaced XML)
        if not extensions:
            extensions = self._root.findall('.//extension')
            logger.debug(f"Found {len(extensions)} extensions using ElementTree in {plugin_info.name}")
        
        for extension in extensions:
            self._parse_extension_element(extension, plugin_info)
    
    def _parse_extension_element(self, extension: Any, plugin_info: PluginInfo) -> None:
        """Parse a single extension element."""
        ext_point = extension.get('point', '')
        ext_id = extension.get('id', '')
        ext_name = extension.get('name', '')
        
        ext = PluginExtension(
            point=ext_point,
            id=ext_id,
            name=ext_name
        )
        
        # Extract module info
        module = extension.find('module')
        if module is not None:
            self._parse_module(module, plugin_info)
        
        # Extract generator info
        generator = extension.find('generator')
        if generator is not None:
            ext.generator_class = generator.get('class', '')
            ext.module_id = generator.get('moduleId', '')
            ext.modes = generator.get('modes', '')
            
            for param in generator.findall('parameter'):
                name = param.get('name', '')
                value = param.get('value', '')
                mode = param.get('mode', '')
                key = name if not mode else f"{name}[{mode}]"
                ext.parameters[key] = value
        
        # Extract configuration
        config = extension.find('configuration')
        if config is not None:
            schema = config.find('schema')
            if schema is not None:
                resource = schema.find('resource')
                if resource is not None:
                    ext.schema_resource = resource.get('value', '')
                    ext.schema_type = resource.get('type', '')
        
        # Extract TOC
        toc = extension.find('toc')
        if toc is not None:
            ext.toc_file = toc.get('file', '')
        
        plugin_info.extensions.append(ext)
    
    def _parse_module(self, module: Any, plugin_info: PluginInfo) -> None:
        """Parse module element."""
        plugin_info.module_id = module.get('id', '')
        plugin_info.module_label = module.get('label', '')
        plugin_info.description = module.get('description', '')
        plugin_info.category_type = module.get('categoryType', '')
        plugin_info.category_layer = module.get('categoryLayer', '')
        plugin_info.category_category = module.get('categoryCategory', '')
        plugin_info.category_component = module.get('categoryComponent', '')
        
        # Build version strings
        sw_parts = [
            module.get('swVersionMajor', ''),
            module.get('swVersionMinor', ''),
            module.get('swVersionPatch', ''),
            module.get('swVersionSuffix', '')
        ]
        plugin_info.sw_version = '.'.join(filter(None, sw_parts[:3])) + sw_parts[3]
        
        spec_parts = [
            module.get('specVersionMajor', ''),
            module.get('specVersionMinor', ''),
            module.get('specVersionPatch', ''),
            module.get('specVersionSuffix', '')
        ]
        plugin_info.spec_version = '.'.join(filter(None, spec_parts[:3])) + spec_parts[3]
        
        rel_parts = [
            module.get('relVersionPrefix', ''),
            module.get('relVersionMajor', ''),
            module.get('relVersionMinor', ''),
            module.get('relVersionPatch', ''),
            module.get('relVersionSuffix', '')
        ]
        plugin_info.rel_version = ' '.join(filter(None, rel_parts))
        
        # Extract ECU type
        ecu_type = module.find('ecuType')
        if ecu_type is not None:
            plugin_info.target = ecu_type.get('target', '')
            plugin_info.derivate = ecu_type.get('derivate', '')


# ============================================================================
# MANIFEST.MF PARSER
# ============================================================================

class ManifestParser:
    """Parse META-INF/MANIFEST.MF for bundle info and dependencies."""
    
    def __init__(self, plugin_path: Path):
        self.plugin_path = plugin_path
        self.manifest_path = plugin_path / "META-INF" / "MANIFEST.MF"
    
    def parse(self) -> Dict[str, Any]:
        """Extract bundle metadata and dependencies."""
        result = {
            'bundle_name': '',
            'bundle_version': '',
            'bundle_vendor': '',
            'dependencies': []
        }
        
        if not self.manifest_path.exists():
            return result
        
        try:
            content = self.manifest_path.read_text(encoding='utf-8', errors='replace')
            
            # Parse each line (continuation lines start with space)
            lines = []
            for line in content.split('\n'):
                if line.startswith(' ') or line.startswith('\t'):
                    # Continuation of previous line
                    if lines:
                        lines[-1] += ' ' + line.strip()
                else:
                    lines.append(line.strip())
            
            for line in lines:
                if not line or line.startswith('#'):
                    continue
                
                if ':' in line:
                    key, value = line.split(':', 1)
                    key = key.strip()
                    value = value.strip()
                    
                    if key == 'Bundle-Name':
                        result['bundle_name'] = value
                    elif key == 'Bundle-Version':
                        result['bundle_version'] = value
                    elif key == 'Bundle-Vendor':
                        result['bundle_vendor'] = value
                    elif key == 'Require-Bundle':
                        # Parse comma-separated bundle specifications
                        for bundle in value.split(','):
                            bundle = bundle.strip()
                            if bundle:
                                # Extract bundle name (before version specification)
                                bundle_name = re.split(r'[;:=]', bundle)[0].strip()
                                if bundle_name:
                                    result['dependencies'].append(bundle_name)
                    elif key == 'Import-Package':
                        # Also capture Import-Package as dependencies
                        for pkg in value.split(','):
                            pkg = pkg.strip()
                            if pkg:
                                pkg_name = re.split(r'[;:=]', pkg)[0].strip()
                                if pkg_name and pkg_name not in result['dependencies']:
                                    result['dependencies'].append(pkg_name)
                                    
        except Exception as e:
            logger.debug(f"Error parsing MANIFEST.MF: {e}")
        
        return result


# ============================================================================
# ANCHORS XML PARSER
# ============================================================================

class AnchorsXmlParser:
    """Parse anchors.xml for documentation links."""
    
    def __init__(self, plugin_path: Path):
        self.plugin_path = plugin_path
        self.anchors_path = plugin_path / "anchors.xml"
    
    def parse(self) -> List[Dict[str, str]]:
        """Extract documentation links."""
        links = []
        
        if not self.anchors_path.exists():
            return links
        
        try:
            content = self.anchors_path.read_text(encoding='utf-8')
            clean_content = RE_XML_COMMENT.sub('', content)
            root = ET.fromstring(clean_content)
            
            for toc in root.findall('toc'):
                toc_label = toc.get('label', '')
                
                for topic in toc.findall('topic'):
                    links.append({
                        'toc_label': toc_label,
                        'label': topic.get('label', ''),
                        'href': topic.get('href', '')
                    })
                    
        except Exception as e:
            logger.warning(f"Error parsing anchors.xml: {e}")
        
        return links


# ============================================================================
# ANT GENERATOR PARSER
# ============================================================================

class AntGeneratorParser:
    """Parse ant_generator.xml for build targets."""
    
    def __init__(self, plugin_path: Path):
        self.plugin_path = plugin_path
        self.ant_path = plugin_path / "ant_generator.xml"
    
    def parse(self) -> List[str]:
        """Extract build target names."""
        targets = []
        
        if not self.ant_path.exists():
            return targets
        
        try:
            content = self.ant_path.read_text(encoding='utf-8')
            clean_content = RE_XML_COMMENT.sub('', content)
            root = ET.fromstring(clean_content)
            
            for target in root.findall('.//target'):
                name = target.get('name', '')
                if name:
                    targets.append(name)
                    
        except Exception as e:
            logger.warning(f"Error parsing ant_generator.xml: {e}")
        
        return targets


# ============================================================================
# BUILD.PROPERTIES PARSER
# ============================================================================

class BuildPropertiesParser:
    """Parse build.properties for build information."""
    
    def __init__(self, plugin_path: Path):
        self.plugin_path = plugin_path
        self.build_props_path = plugin_path / "build.properties"
    
    def parse(self) -> Dict[str, Any]:
        """Extract build properties."""
        result = {
            'source_folders': [],
            'bin_includes': [],
            'jars_compile': []
        }
        
        if not self.build_props_path.exists():
            return result
        
        try:
            content = self.build_props_path.read_text(encoding='utf-8', errors='replace')
            
            for line in content.split('\n'):
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                
                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip()
                    
                    if key == 'source.':
                        result['source_folders'].append(value)
                    elif key == 'bin.includes':
                        result['bin_includes'].extend(v.strip() for v in value.split(','))
                    elif key == 'jars.compile.classpath':
                        result['jars_compile'].extend(v.strip() for v in value.split(','))
                        
        except Exception as e:
            logger.debug(f"Error parsing build.properties: {e}")
        
        return result


# ============================================================================
# XDM FILE PARSER (Tresos Configuration)
# ============================================================================

class XdmParser:
    """Parse .xdm files for Tresos module configuration."""
    
    def __init__(self, xdm_path: Path):
        self.xdm_path = xdm_path
    
    def parse(self) -> Dict[str, Any]:
        """Extract configuration from .xdm file."""
        result = {
            'filename': self.xdm_path.name,
            'module': '',
            'containers': [],
            'parameters': []
        }
        
        if not self.xdm_path.exists():
            return result
        
        try:
            content = self.xdm_path.read_text(encoding='utf-8', errors='replace')
            clean_content = RE_XML_COMMENT.sub('', content)
            root = ET.fromstring(clean_content)
            
            # Extract module name from root element
            result['module'] = root.tag
            
            # Extract container definitions
            for container in root.findall('.//CONTAINER'):
                container_name = container.get('SHORT-NAME', '')
                params = {}
                
                # Extract parameters within container
                for param in container:
                    param_name = param.tag
                    param_value = param.get('VALUE', '') or param.text or ''
                    if param_name != 'SHORT-NAME':
                        params[param_name] = str(param_value).strip()
                
                if container_name:
                    result['containers'].append({
                        'name': container_name,
                        'parameters': params
                    })
            
            # Extract top-level parameters
            for elem in root:
                if elem.tag not in ('CONTAINER', 'MODULE', 'AR-PACKAGE'):
                    value = elem.get('VALUE', '') or elem.text or ''
                    if value:
                        result['parameters'].append({
                            'name': elem.tag,
                            'value': str(value).strip()
                        })
                        
        except Exception as e:
            logger.debug(f"Error parsing .xdm file {self.xdm_path}: {e}")
        
        return result


# ============================================================================
# C/H FILE PARSER (using pycparser)
# ============================================================================

# Try to import pycparser, fall back to regex if not available
try:
    import pycparser
    from pycparser import c_parser, c_ast, c_generator
    import cffi
    HAS_PYCPARSER = True
    HAS_CFFI = True
except ImportError:
    HAS_PYCPARSER = False
    HAS_CFFI = False
    logger.warning("pycparser/cffi not installed. Using fallback regex parser.")

# Try to import PDF library
try:
    from PyPDF2 import PdfReader
    HAS_PYPDF2 = True
except ImportError:
    HAS_PYPDF2 = False
    logger.warning("PyPDF2 not installed. PDF extraction disabled.")

# Try to import lxml for better XML namespace handling
try:
    from lxml import etree as lxml_ET
    HAS_LXML = True
except ImportError:
    HAS_LXML = False


class DoxygenParser:
    """Parse Doxygen-style documentation comments."""
    
    # Match doxygen comment blocks
    COMMENT_PATTERN = r'/\*\*\s*\n((?:[ \t]+\*[^\n]*\n)+)[ \t]*\*/'
    
    @classmethod
    def extract_doc(cls, content: str, position: int) -> str:
        """Extract documentation from position back to find comment."""
        search_start = max(0, position - 2000)
        search_content = content[search_start:position]
        
        match = re.search(cls.COMMENT_PATTERN, search_content, re.DOTALL)
        if match:
            doc = match.group(1)
            doc = re.sub(r'^[ \t]+\*', '', doc, flags=re.MULTILINE).strip()
            return doc
        return ""
    
    @classmethod
    def parse_docstring(cls, doc: str) -> Dict[str, str]:
        """Parse doxygen tags from documentation."""
        result = {
            'brief': '',
            'description': '',
            'param': {},
            'return': '',
            'pre': '',
            'post': ''
        }
        
        if not doc:
            return result
        
        lines = doc.split('\n')
        current_key = 'brief'
        param_buffer = []
        
        for line in lines:
            line = line.strip()
            
            # Handle @param
            param_match = re.match(r'@param\s+\[?(in|out|in,out)\]?\s+(\w+)\s*(.*)', line)
            if param_match:
                if param_buffer:
                    result['param'][param_buffer[0]] = ' '.join(param_buffer[1:])
                    param_buffer = []
                param_buffer = [param_match.group(2), param_match.group(3)]
                current_key = 'param'
                continue
            
            # Handle other tags
            tag_match = re.match(r'@(return|retval|pre|post|brief|details)\s+(.*)', line)
            if tag_match:
                if param_buffer:
                    result['param'][param_buffer[0]] = ' '.join(param_buffer[1:])
                    param_buffer = []
                tag = tag_match.group(1)
                value = tag_match.group(2)
                if tag in ('return', 'retval'):
                    current_key = 'return'
                    result['return'] = value
                elif tag == 'pre':
                    result['pre'] = value
                elif tag == 'post':
                    result['post'] = value
                elif tag in ('brief', 'details'):
                    result['brief'] = value
                continue
            
            # Regular text
            if line and not line.startswith('@'):
                if current_key == 'brief' and not result['brief']:
                    result['brief'] = line
                elif param_buffer:
                    param_buffer.append(line)
        
        # Handle remaining param
        if param_buffer:
            result['param'][param_buffer[0]] = ' '.join(param_buffer[1:])
        
        return result


class CFileParser:
    """Parse C source files using pycparser or regex fallback."""
    
    def __init__(self, filepath: Path):
        self.filepath = filepath
        self._content: Optional[str] = None
        self._version: VersionInfo = VersionInfo()
        self._functions: List[ApiFunction] = []
        self._local_functions: List[str] = []
        self._macros: List[Tuple[str, str]] = []
        self._includes: List[str] = []
        self._doc: str = ""
    
    def parse(self) -> SourceFile:
        """Parse the C file and return SourceFile."""
        if not self.filepath.exists():
            return SourceFile(path=self.filepath, filename=self.filepath.name)
        
        try:
            self._content = self.filepath.read_text(encoding='utf-8', errors='replace')
            self._extract_version()
            self._extract_includes()
            self._extract_macros()
            
            if HAS_PYCPARSER:
                self._parse_with_pycparser()
            else:
                self._parse_with_regex()
            
            self._doc = DoxygenParser.extract_doc(self._content, len(self._content))
            
        except Exception as e:
            logger.warning(f"Error parsing C file {self.filepath}: {e}")
        
        return SourceFile(
            path=self.filepath,
            filename=self.filepath.name,
            version=self._version,
            functions=self._functions,
            local_functions=self._local_functions,
            macros=self._macros,
            includes=self._includes,
            doc=self._doc
        )
    
    def _extract_version(self) -> None:
        """Extract version information using regex."""
        patterns = [
            ('vendor_id', r'#define\s+(\w+_VENDOR_ID_C)\s+(\d+)'),
            ('ar_major', r'#define\s+(\w+_AR_RELEASE_MAJOR_VERSION_C)\s+(\d+)'),
            ('ar_minor', r'#define\s+(\w+_AR_RELEASE_MINOR_VERSION_C)\s+(\d+)'),
            ('ar_patch', r'#define\s+(\w+_AR_RELEASE_REVISION_VERSION_C)\s+(\d+)'),
            ('sw_major', r'#define\s+(\w+_SW_MAJOR_VERSION_C)\s+(\d+)'),
            ('sw_minor', r'#define\s+(\w+_SW_MINOR_VERSION_C)\s+(\d+)'),
            ('sw_patch', r'#define\s+(\w+_SW_PATCH_VERSION_C)\s+(\d+)'),
        ]
        
        for attr, pattern in patterns:
            match = re.search(pattern, self._content or '')
            if match:
                setattr(self._version, attr, match.group(2))
    
    def _extract_includes(self) -> None:
        """Extract #include statements."""
        if not self._content:
            return
        self._includes = RE_INCLUDE.findall(self._content or '')
    
    def _extract_macros(self) -> None:
        """Extract important #define macros."""
        if not self._content:
            return
        
        # Find version/error/API related defines
        macro_pattern = r'#define\s+(\w+)\s+\(?([^/\n]+?)\)?(?:\s*/\*.*?\*/)?\s*$'
        for match in re.finditer(macro_pattern, self._content, re.MULTILINE):
            name, value = match.groups()
            if any(kw in name for kw in ['ID', 'ERROR', 'API', 'MODULE', 'VERSION']):
                self._macros.append((name, value.strip()))
    
    def _parse_with_pycparser(self) -> None:
        """Parse using pycparser AST."""
        try:
            original_content = self._content or ''
            
            # Check heuristics: if file has many includes/complex preprocessor, skip pycparser
            include_count = original_content.count('#include')
            ifdef_count = original_content.count('#if') + original_content.count('#ifdef') + original_content.count('#ifndef')
            
            # If file is too complex for pycparser, use regex directly
            # Lower threshold since pycparser has strict comment requirements
            if include_count > 5 or (ifdef_count > 3 and include_count > 2):
                logger.debug(f"File {self.filepath.name} too complex for pycparser ({include_count} includes, {ifdef_count} ifdefs), using regex")
                self._parse_with_regex()
                return
            
            content = self._remove_comments(original_content)
            
            # Remove large header comment blocks (autosar-style headers)
            content = self._remove_autosar_header(content)
            
            # Process #if blocks but keep it simple
            content = self._preprocess_if_blocks(content)
            
            # Add fake AUTOSAR type definitions for pycparser
            fake_typedefs = self._get_autosar_typedefs()
            processed_content = fake_typedefs + '\n' + content
            
            # Direct pycparser parsing
            from pycparser import c_parser, c_ast
            parser = c_parser.CParser()
            ast = parser.parse(processed_content, filename=self.filepath.name)
            self._visit_ast(ast)
            
        except Exception as e:
            # If pycparser fails, fall back to regex (log as warning for visibility)
            logger.warning(f"Pycparser failed for {self.filepath.name}: {e}, using regex fallback")
            self._parse_with_regex()
    
    def _preprocess_if_blocks(self, content: str) -> str:
        """Handle #if blocks for pycparser by keeping content."""
        lines = []
        in_if_block = False
        if_depth = 0
        
        for line in content.split('\n'):
            stripped = line.strip()
            
            # Skip #include
            if stripped.startswith('#include'):
                continue
            
            # Handle #if/#ifdef/#ifndef
            if stripped.startswith('#if') or stripped.startswith('#ifdef') or stripped.startswith('#ifndef'):
                in_if_block = True
                if_depth += 1
                # Skip the #if line
                continue
            elif stripped.startswith('#endif'):
                if_depth = max(0, if_depth - 1)
                if if_depth == 0:
                    in_if_block = False
                continue
            elif stripped.startswith('#else') or stripped.startswith('#elif'):
                continue
            elif stripped.startswith('#'):
                # Other preprocessor directives - skip
                continue
            
            # Skip #pragma
            if stripped.startswith('#pragma'):
                continue
            
            # If in if block or regular line, keep it
            if in_if_block or (not stripped.startswith('#') and stripped):
                lines.append(line)
        
        return '\n'.join(lines)
    
    def _remove_autosar_header(self, content: str) -> str:
        """Remove large AUTOSAR-style header comment blocks."""
        # Remove patterns like: /*==================...==================*/
        # These are typically at the top of AUTOSAR files
        lines = content.split('\n')
        result_lines = []
        skip_mode = False
        skip_blank_count = 0
        
        for line in lines:
            # Check if line is part of a header comment block
            stripped = line.strip()
            if stripped.startswith('/*==') or stripped.startswith('/*-'):
                skip_mode = True
                skip_blank_count = 0
                continue
            elif skip_mode:
                if stripped.startswith('*/') or stripped.startswith('*-') or stripped.startswith('=='):
                    skip_mode = False
                    continue
                else:
                    continue
            else:
                if stripped == '':
                    skip_blank_count += 1
                    if skip_blank_count <= 2:  # Keep max 2 blank lines
                        result_lines.append(line)
                else:
                    skip_blank_count = 0
                    result_lines.append(line)
        
        return '\n'.join(result_lines)
    
    def _get_autosar_typedefs(self) -> str:
        """Get fake AUTOSAR typedefs for pycparser to parse AUTOSAR headers."""
        return '''
/* Fake AUTOSAR type definitions for pycparser */
typedef unsigned char uint8;
typedef unsigned short uint16;
typedef unsigned int uint32;
typedef unsigned long long uint64;
typedef signed char sint8;
typedef signed short sint16;
typedef signed int sint32;
typedef signed long long sint64;
typedef uint8 boolean;
typedef uint8 uint8_least;
typedef uint16 uint16_least;
typedef uint32 uint32_least;
typedef sint8 sint8_least;
typedef sint16 sint16_least;
typedef sint32 sint32_least;
typedef uint32 Std_ReturnType;
typedef uint8 Dio_LevelType;
typedef uint8 Dio_PortLevelType;
typedef uint16 Dio_ChannelType;
typedef uint8 Dio_PortType;
typedef uint16 Dio ChannelGroupType;
typedef uint32 Can_IdType;
typedef uint16 Can_HwHandleType;
typedef uint8 CanIfControllerIdType;
typedef uint16 PduIdType;
typedef uint16 PduLengthType;
typedef void* PduInfoType;
typedef uint8 I2C_StatusType;
typedef uint8 UART_StatusType;
typedef uint16 Mcu_ClockType;
typedef uint8 Port_PinType;
typedef uint8 Port_PinModeType;
typedef uint8 Dio_PinDirectionType;
typedef uint8 Dio_LevelType;
typedef uint16 Spi_DataType;
typedef uint8 SpiChannelType;
typedef uint8 SpiJobType;
typedef uint16 SpiSequenceType;
typedef uint8 Can_IdType;
typedef uint8 CanIf_PduModeType;
typedef uint8 CanIf_TrcvModeType;
typedef void (*CanIf_UserTxConfirmationPtrType)(uint16 id, uint8 channel);
typedef void (*CanIf_UserRxIndicationPtrType)(uint16 id, uint8 channel, uint8* data, uint16 length);
'''
    
    def _preprocess_for_pycparser(self, content: str) -> str:
        """Simple preprocessing to handle common AUTOSAR preprocessor directives."""
        if not content:
            return ""
        
        lines = []
        in_if_block = False
        
        for line in content.split('\n'):
            stripped = line.strip()
            
            # Skip #include directives (pycparser doesn't support them)
            if stripped.startswith('#include'):
                continue  # Simply skip, don't add any comment
            
            # Skip #pragma directives
            if stripped.startswith('#pragma'):
                continue
            
            # Handle conditional compilation simply
            if stripped.startswith('#if') or stripped.startswith('#ifdef') or stripped.startswith('#ifndef'):
                # Keep the condition but simplify - assume true for parsing
                in_if_block = True
                lines.append(f"/* {stripped} */ 1")
            elif stripped.startswith('#else') or stripped.startswith('#elif'):
                lines.append(f"/* {stripped} */ 1")
            elif stripped.startswith('#endif'):
                in_if_block = False
                lines.append("")
            elif stripped.startswith('#define') and not stripped.startswith('#define ') and '/*' not in stripped:
                # Skip complex macros that may cause issues
                continue
            elif in_if_block and not stripped.startswith('#'):
                # Keep content in #if blocks
                lines.append(line)
            else:
                lines.append(line)
        
        return '\n'.join(lines)
    
    def _remove_comments(self, content: str) -> str:
        """Remove C-style comments from content for pycparser."""
        # Use a proper state machine approach for comment removal
        result = []
        i = 0
        length = len(content)
        
        while i < length:
            # Check for /* ... */ multi-line comment
            if i < length - 1 and content[i] == '/' and content[i + 1] == '*':
                # Find end of comment
                j = i + 2
                while j < length - 1:
                    if content[j] == '*' and content[j + 1] == '/':
                        break
                    j += 1
                i = j + 2  # Skip past */
            # Check for // single-line comment
            elif i < length - 1 and content[i] == '/' and content[i + 1] == '/':
                # Skip until end of line
                while i < length and content[i] != '\n':
                    i += 1
                continue  # Don't increment i again
            else:
                result.append(content[i])
                i += 1
        
        return ''.join(result)
    
    def _visit_ast(self, node: Any, is_static: bool = False) -> None:
        """Visit AST nodes recursively."""
        if node is None:
            return
        
        class Visitor(c_ast.NodeVisitor):
            def __init__(outer_self):
                outer_self.local_funcs = []
                outer_self.public_funcs = []
                outer_self.content = self._content
                outer_self.local_only = is_static
            
            def visit_FuncDef(outer_self, node):
                decl = node.decl
                name = decl.name
                if not name or name.startswith('_'):
                    return
                
                # Check if static
                quals = decl.quals if hasattr(decl, 'quals') else []
                is_local = 'static' in quals
                
                # Get docstring
                doc = DoxygenParser.extract_doc(outer_self.content, decl.coord.line if decl.coord else 0)
                parsed_doc = DoxygenParser.parse_docstring(doc)
                
                # Get return type
                ret_type = ""
                if isinstance(decl.type, c_ast.FuncDecl):
                    if decl.type.typename:
                        ret_type = self._get_type_name(decl.type.typename)
                    elif isinstance(decl.type.type, c_ast.TypeDecl):
                        ret_type = self._get_type_name(decl.type.type)
                
                # Get parameters
                params = []
                if isinstance(decl.type, c_ast.FuncDecl) and decl.type.args:
                    for param in decl.type.args.params:
                        pname = param.name if hasattr(param, 'name') else ''
                        ptype = self._get_type_name(param.type) if hasattr(param, 'type') else ''
                        if pname:
                            params.append((ptype, pname))
                
                func = ApiFunction(
                    name=name,
                    return_type=ret_type,
                    params=params,
                    brief=parsed_doc.get('brief', ''),
                    description=parsed_doc.get('description', ''),
                    preconditions=parsed_doc.get('pre', ''),
                    postconditions=parsed_doc.get('post', ''),
                    return_desc=parsed_doc.get('return', ''),
                    is_public=not is_local
                )
                
                if is_local:
                    outer_self.local_funcs.append(name)
                else:
                    outer_self.public_funcs.append(func)
        
        visitor = Visitor()
        visitor.visit(node)
        self._local_functions.extend(visitor.local_funcs)
        self._functions.extend(visitor.public_funcs)
    
    def _get_type_name(self, type_node: Any) -> str:
        """Get type name from AST node."""
        if type_node is None:
            return ""
        
        if isinstance(type_node, c_ast.TypeDecl):
            if type_node.declname:
                return type_node.declname
            return self._get_type_name(type_node.type)
        
        if isinstance(type_node, c_ast.PtrDecl):
            base = self._get_type_name(type_node.type)
            return f"{base}*" if base else "void*"
        
        if isinstance(type_node, c_ast.IdentifierType):
            return ' '.join(type_node.names)
        
        if isinstance(type_node, c_ast.FuncDecl):
            return "function"
        
        return str(type_node)
    
    def _parse_with_regex(self) -> None:
        """Fallback regex-based parser with improved pattern matching."""
        if not self._content:
            return
        
        # First, remove preprocessor lines to avoid false matches
        # Keep track of positions to search backwards for docstrings
        clean_content = self._remove_preprocessor(self._content)
        
        # Pattern for function definitions - more precise
        func_pattern = (
            r'(?:(/\*\*[\s\S]*?\*/)\s*)?'  # Optional doxygen doc (group 1)
            r'\b((?:static\s+)?(?:inline\s+)?(?:const\s+)?(?:void|uint8|uint16|uint32|uint64|'
            r'int8|int16|int32|int64|boolean|Std_ReturnType|Dio_|Siul2_|'
            r'[A-Z][A-Za-z0-9_]*)\s*\*?\s*)\s*'  # Return type (group 2)
            r'(\w+)\s*\(\s*'  # Function name (group 3)
            r'([^)]*)\s*\)\s*'  # Parameters (group 4)
            r'(?:\{|;)'  # Function body start or declaration end
        )
        
        seen_functions = set()
        
        for match in re.finditer(func_pattern, clean_content, re.MULTILINE):
            doc_match = match.group(1)
            ret_type = match.group(2).strip()
            name = match.group(3).strip()
            params = match.group(4).strip()
            
            # Skip invalid matches
            if not name or name.startswith('_') or len(name) < 3:
                continue
            
            # Skip if already seen (avoid duplicates)
            if name in seen_functions:
                continue
            seen_functions.add(name)
            
            # Skip keywords and control structures
            if name in ('if', 'else', 'while', 'for', 'switch', 'case', 
                       'return', 'break', 'continue', 'sizeof', 'typedef'):
                continue
            
            # Skip macro-like names (all caps with underscores)
            if name.isupper() and '_' in name:
                continue
            
            # Skip type names (usually TitleCase without underscore)
            if name[0].isupper() and '_' not in name and name not in ('Dio', 'Siul2'):
                continue
            
            # Skip validation-type function patterns (common in AUTOSAR)
            if any(x in name for x in ['Validate', 'Check', 'Assert', 'Report']):
                # These are local validation functions
                self._local_functions.append(name)
                continue
            
            is_static = 'static' in ret_type
            
            # Parse parameters
            param_list = []
            if params and params != 'void':
                # Split by comma but be careful with nested structures
                depth = 0
                current_param = []
                for char in params:
                    if char in '(<':
                        depth += 1
                        current_param.append(char)
                    elif char in ')>':
                        depth -= 1
                        current_param.append(char)
                    elif char == ',' and depth == 0:
                        param_str = ''.join(current_param).strip()
                        if param_str:
                            param_list.extend(self._parse_param(param_str))
                        current_param = []
                    else:
                        current_param.append(char)
                
                # Handle last parameter
                param_str = ''.join(current_param).strip()
                if param_str:
                    param_list.extend(self._parse_param(param_str))
            
            # Parse docstring if available
            brief = ""
            if doc_match:
                doc = doc_match.strip()
                doc = re.sub(r'^/\*\*|\*/$', '', doc)
                doc = re.sub(r'^\s*\*\s?', '', doc, flags=re.MULTILINE).strip()
                brief_match = re.search(r'@brief\s+(.+?)(?:\n|$)', doc)
                if brief_match:
                    brief = brief_match.group(1).strip()
                elif len(doc) > 3:
                    brief = doc.split('\n')[0][:100]
            
            func = ApiFunction(
                name=name,
                return_type=ret_type,
                params=param_list,
                brief=brief,
                is_public=not is_static
            )
            
            if is_static:
                self._local_functions.append(name)
            else:
                self._functions.append(func)
    
    def _parse_param(self, param_str: str) -> List[Tuple[str, str]]:
        """Parse a single parameter string into type and name."""
        parts = param_str.strip().split()
        if len(parts) >= 2:
            # Last part is usually the name
            ptype = ' '.join(parts[:-1])
            pname = parts[-1]
            # Clean up pointer/reference
            pname = re.sub(r'[\*\s]+$', '', pname)
            if pname and pname not in ('void', ''):
                return [(ptype, pname)]
        return []
    
    def _remove_preprocessor(self, content: str) -> str:
        """Remove preprocessor directives that could cause false matches."""
        # Remove #if, #ifdef, #ifndef blocks
        result = []
        lines = content.split('\n')
        skip_depth = 0
        
        for line in lines:
            stripped = line.strip()
            
            # Track preprocessor depth
            if re.match(r'^\s*#\s*if', stripped):
                skip_depth += 1
                continue
            elif re.match(r'^\s*#\s*else', stripped) and skip_depth > 0:
                continue  # Skip else in skipped block
            elif re.match(r'^\s*#\s*endif', stripped):
                skip_depth = max(0, skip_depth - 1)
                continue
            elif re.match(r'^\s*#\s*define', stripped):
                continue  # Skip defines
            
            if skip_depth > 0:
                continue
            
            result.append(line)
        
        return '\n'.join(result)


class HFileParser:
    """Parse header files for public API."""
    
    def __init__(self, filepath: Path):
        self.filepath = filepath
        self._content: Optional[str] = None
        self._version: VersionInfo = VersionInfo()
        self._public_functions: List[ApiFunction] = []
        self._error_codes: List[ErrorCode] = []
        self._api_ids: List[Tuple[str, str]] = []
        self._macros: List[Tuple[str, str]] = []
        self._includes: List[str] = []
        self._structs: List[Tuple[str, str]] = []
        self._enums: List[Tuple[str, str]] = []
        self._typedefs: List[Tuple[str, str]] = []
        self._doc: str = ""
    
    def parse(self) -> HeaderFile:
        """Parse the header file."""
        if not self.filepath.exists():
            return HeaderFile(path=self.filepath, filename=self.filepath.name)
        
        try:
            self._content = self.filepath.read_text(encoding='utf-8', errors='replace')
            self._extract_version()
            self._extract_includes()
            self._extract_error_codes()
            self._extract_api_ids()
            self._extract_macros()
            self._extract_structs()
            self._extract_enums()
            self._extract_typedefs()
            self._extract_functions()
            
            self._doc = DoxygenParser.extract_doc(self._content, len(self._content))
            
        except Exception as e:
            logger.warning(f"Error parsing H file {self.filepath}: {e}")
        
        return HeaderFile(
            path=self.filepath,
            filename=self.filepath.name,
            version=self._version,
            public_functions=self._public_functions,
            error_codes=self._error_codes,
            api_ids=self._api_ids,
            macros=self._macros,
            includes=self._includes,
            structs=self._structs,
            enums=self._enums,
            typedefs=self._typedefs,
            doc=self._doc
        )
    
    def _extract_version(self) -> None:
        """Extract version info."""
        patterns = [
            ('vendor_id', r'#define\s+(\w+_VENDOR_ID)\s+(\d+)'),
            ('module_id', r'#define\s+(\w+_MODULE_ID)\s+(\d+)'),
            ('ar_major', r'#define\s+(\w+_AR_RELEASE_MAJOR_VERSION)\s+(\d+)'),
            ('ar_minor', r'#define\s+(\w+_AR_RELEASE_MINOR_VERSION)\s+(\d+)'),
            ('ar_patch', r'#define\s+(\w+_AR_RELEASE_REVISION_VERSION)\s+(\d+)'),
            ('sw_major', r'#define\s+(\w+_SW_MAJOR_VERSION)\s+(\d+)'),
            ('sw_minor', r'#define\s+(\w+_SW_MINOR_VERSION)\s+(\d+)'),
            ('sw_patch', r'#define\s+(\w+_SW_PATCH_VERSION)\s+(\d+)'),
        ]
        
        for attr, pattern in patterns:
            match = re.search(pattern, self._content or '')
            if match:
                setattr(self._version, attr, match.group(2))
    
    def _extract_includes(self) -> None:
        """Extract includes."""
        if not self._content:
            return
        self._includes = RE_INCLUDE.findall(self._content or '')
    
    def _extract_error_codes(self) -> None:
        """Extract error code definitions."""
        if not self._content:
            return
        
        # Match doxygen comment + #define
        error_pattern = (
            r'/\*\*\s*\n'               # Start comment
            r'(?:[ \t]+\*[^\n]*\n)+'    # Comment lines
            r'[ \t]*\*/\s*\n'           # End comment
            r'#define\s+(\w+)\s+\(([^)]+)\)'  # Define
        )
        
        for match in re.finditer(error_pattern, self._content, re.DOTALL):
            name = match.group(1)
            value = match.group(2)
            
            # Get description from comment before
            start = match.start()
            doc = DoxygenParser.extract_doc(self._content[:start], start)
            desc_match = re.search(r'@brief\s+(.+?)(?:\n|$)', doc)
            desc = desc_match.group(1) if desc_match else ''
            
            self._error_codes.append(ErrorCode(
                name=name,
                value=value,
                description=desc
            ))
    
    def _extract_api_ids(self) -> None:
        """Extract API service IDs."""
        if not self._content:
            return
        
        api_pattern = (
            r'/\*\*\s*\n'               # Start comment
            r'(?:[ \t]+\*[^\n]*\n)+'   # Comment lines
            r'[ \t]*\*/\s*\n'          # End comment
            r'#define\s+(\w+_ID)\s+\(([^)]+)\)'
        )
        
        for match in re.finditer(api_pattern, self._content, re.DOTALL):
            self._api_ids.append((match.group(1), match.group(2)))
    
    def _extract_macros(self) -> None:
        """Extract macro definitions with values."""
        if not self._content:
            return
        
        # Match #define NAME VALUE patterns (not function-like macros)
        macro_pattern = r'#define\s+(\w+)\s+(.+?)(?:\s*(?:\r?\n|//|/\*|$))'
        seen_names = set()
        
        for match in re.finditer(macro_pattern, self._content, re.DOTALL):
            macro_name = match.group(1)
            macro_value = match.group(2).strip()
            
            # Skip if it's a function-like macro (has parentheses immediately after)
            next_char = self._content[match.end():match.end()+1]
            if next_char == '(':
                continue
            
            # Skip if already seen
            if macro_name in seen_names:
                continue
            seen_names.add(macro_name)
            
            # Clean up value - remove trailing slashes and join lines
            macro_value = macro_value.replace('\\\n', ' ').replace('\\\r\n', ' ')
            macro_value = ' '.join(macro_value.split())
            
            # Skip empty values or comments
            if macro_value and not macro_value.startswith('//') and not macro_value.startswith('/*'):
                self._macros.append((macro_name, macro_value))
    
    def _extract_structs(self) -> None:
        """Extract struct definitions."""
        if not self._content:
            return
        
        # Match struct definitions: struct Name { ... };
        struct_pattern = r'(?:typedef\s+)?struct\s+(\w+)\s*\{([^}]*)\}'
        for match in re.finditer(struct_pattern, self._content, re.DOTALL):
            struct_name = match.group(1)
            fields_text = match.group(2)
            
            # Extract field names and types
            fields = []
            field_lines = fields_text.split(';')
            for line in field_lines:
                line = line.strip()
                if not line or line.startswith('/*') or line.startswith('//'):
                    continue
                # Extract field type and name
                parts = line.split()
                if len(parts) >= 2:
                    field_type = ' '.join(parts[:-1])
                    field_name = parts[-1].rstrip('*')
                    field_name = field_name.strip()
                    if field_name and not field_name.startswith('*'):
                        fields.append(f"{field_type} {field_name}")
            
            fields_summary = ', '.join(fields[:5])
            if len(fields) > 5:
                fields_summary += f" (+{len(fields)-5} more)"
            
            self._structs.append((struct_name, fields_summary))
    
    def _extract_enums(self) -> None:
        """Extract enum definitions."""
        if not self._content:
            return
        
        # Match enum definitions: enum Name { ... };
        enum_pattern = r'(?:typedef\s+)?enum\s+(\w+)\s*\{([^}]*)\}'
        for match in re.finditer(enum_pattern, self._content, re.DOTALL):
            enum_name = match.group(1)
            values_text = match.group(2)
            
            # Extract enum values
            values = []
            for val_match in re.finditer(r'(\w+)\s*(?:=\s*([^,}]+))?', values_text):
                val_name = val_match.group(1)
                val_value = val_match.group(2)
                if val_value:
                    values.append(f"{val_name}={val_value.strip()}")
                else:
                    values.append(val_name)
            
            values_summary = ', '.join(values[:10])
            if len(values) > 10:
                values_summary += f" (+{len(values)-10} more)"
            
            self._enums.append((enum_name, values_summary))
    
    def _extract_typedefs(self) -> None:
        """Extract typedef declarations."""
        if not self._content:
            return
        
        # Match typedef declarations
        typedef_pattern = r'typedef\s+(.+?)\s+(\w+)\s*;'
        for match in re.finditer(typedef_pattern, self._content, re.DOTALL):
            original_type = match.group(1).strip()
            alias = match.group(2).strip()
            
            # Skip function pointer typedefs (too complex)
            if '(' not in original_type and ')' not in original_type:
                self._typedefs.append((alias, original_type))
    
    def _extract_functions(self) -> None:
        """Extract public function declarations."""
        if not self._content:
            return
        
        # Remove comments to avoid false matches
        clean_content = RE_C_MULTILINE_COMMENT.sub('', self._content)
        clean_content = RE_C_SINGLELINE_COMMENT.sub('', clean_content)
        
        # Pattern for function declarations (expanded AUTOSAR types)
        func_pattern = (
            rf'^((?:const\s+)?(?:{RE_FUNC_RETURN_TYPES}|void\*)\s*\*?\s*)\s*'  # Return type
            r'(\w{3,})\s*\(\s*([^)]*)\s*\)\s*;'  # Name and params
        )
        
        seen_funcs = set()
        
        for match in re.finditer(func_pattern, clean_content, re.MULTILINE):
            ret_type = match.group(1).strip()
            name = match.group(2).strip()
            params = match.group(3).strip()
            
            if not name or name in seen_funcs:
                continue
            
            # Skip common non-function patterns
            if any(kw in name.lower() for kw in ['define', 'endif', 'ifdef', 'pragma', 'error']):
                continue
            if name in ('if', 'else', 'while', 'for', 'switch', 'case', 'return', 'sizeof'):
                continue
            if name.isupper() and len(name) > 5:
                continue
            
            seen_funcs.add(name)
            
            # Parse parameters
            param_list = self._parse_params(params)
            
            # Try to get brief from context (look for comment before function)
            # Use original _content (with comments) to find docstrings
            brief = self._get_context_brief(self._content, match.start())
            
            func = ApiFunction(
                name=name,
                return_type=ret_type,
                params=param_list,
                brief=brief,
                description='',
                is_public=True
            )
            
            self._public_functions.append(func)
    
    def _get_context_brief(self, content: str, position: int) -> str:
        """Get brief description from comment before function."""
        if position < 100:
            return ""
        
        # Look back 50-800 chars for a comment (increased from 200)
        search_start = max(0, position - 800)
        search_area = content[search_start:position]
        
        # Try to find doxygen block comment /**
        comment_match = re.search(r'/\*\*(.+?)\*/', search_area, re.DOTALL)
        if comment_match:
            brief = comment_match.group(1)
            brief = re.sub(r'^\s*\*\s?', '', brief, flags=re.MULTILINE).strip()
            brief = re.sub(r'@brief\s+', '', brief)
            brief = brief.split('@')[0].strip()
            return brief[:150] if brief else ""
        
        # Try to find single-line doxygen comment ///
        sl_comment_match = re.search(r'(?://[/!]\s*[^\n]*\n){1,3}\s*$', search_area)
        if sl_comment_match:
            brief = sl_comment_match.group(0)
            brief = re.sub(r'//[/!]\s*', '', brief)
            brief = re.sub(r'@brief\s+', '', brief)
            brief = brief.strip()
            return brief[:150] if brief else ""
        
        return ""
    
    def _parse_params(self, params: str) -> List[Tuple[str, str]]:
        """Parse parameter string into list of (type, name) tuples."""
        param_list = []
        if params and params not in ('void', '', '(void)'):
            params = params.replace('(void)', '').strip()
            if params:
                for p in params.split(','):
                    p = p.strip()
                    if p:
                        p = re.sub(r'\s+', ' ', p)
                        parts = p.split()
                        if len(parts) >= 2:
                            ptype = ' '.join(parts[:-1])
                            pname = parts[-1]
                            pname = re.sub(r'[\*\s]+$', '', pname)
                            if pname and pname not in ('void',):
                                param_list.append((ptype, pname))
        return param_list
    
    def _parse_header_doc(self, doc: str) -> Dict[str, str]:
        """Parse header file documentation."""
        result = {'brief': '', 'description': '', 'return': ''}
        
        # Clean up doc lines
        lines = doc.strip().split('\n')
        clean_lines = []
        for line in lines:
            line = re.sub(r'^\s*\*\s?', '', line)
            clean_lines.append(line)
        
        full_doc = ' '.join(clean_lines)
        
        # Extract @brief
        brief_match = re.search(r'@brief\s+(.+?)(?:\n|@)', full_doc, re.DOTALL)
        if brief_match:
            result['brief'] = brief_match.group(1).strip()
        
        # Extract @return
        return_match = re.search(r'@return[s]?\s+(.+?)(?:\n|@)', full_doc, re.DOTALL)
        if return_match:
            result['return'] = return_match.group(1).strip()
        
        # Use first line as brief if no @brief
        if not result['brief']:
            for line in clean_lines:
                line = line.strip()
                if line and not line.startswith('@') and len(line) > 10:
                    result['brief'] = line[:150]
                    break
        
        return result


# ============================================================================
# SOURCE FILE SCANNER
# ============================================================================

class SourceScanner:
    """Scan plugin directory for source files."""
    
    # Directories to scan for source files
    SOURCE_DIRS = ['src', 'include']
    
    # Directories to exclude from scanning (including generate_PC - auto-generated code)
    EXCLUDE_DIRS = {'examples', 'test', 'tests', 'doc', 'docs', 'documentation',
                    '.git', 'templates', 'scripts', '__pycache__',
                    'generate', 'generated', 'generate_PC'}
    
    # File patterns
    C_PATTERN = '*.c'
    H_PATTERN = '*.h'
    
    def __init__(self, plugin_path: Path, extra_excludes: List[str] = None):
        self.plugin_path = plugin_path
        self.exclude_dirs = set(self.EXCLUDE_DIRS)
        if extra_excludes:
            self.exclude_dirs.update(extra_excludes)
    
    def scan(self) -> Tuple[List[SourceFile], List[HeaderFile]]:
        """Scan for source and header files."""
        source_files: List[SourceFile] = []
        header_files: List[HeaderFile] = []
        
        for src_dir in self.SOURCE_DIRS:
            dir_path = self.plugin_path / src_dir
            if not dir_path.exists():
                continue
            
            # Scan C files
            for c_file in dir_path.glob(self.C_PATTERN):
                if self._should_exclude(c_file):
                    continue
                parser = CFileParser(c_file)
                source_files.append(parser.parse())
            
            # Scan H files
            for h_file in dir_path.glob(self.H_PATTERN):
                if self._should_exclude(h_file):
                    continue
                if '_cfg' in h_file.name.lower():  # Skip generated config files
                    continue
                parser = HFileParser(h_file)
                header_files.append(parser.parse())
        
        # Also scan include in root
        root_include = self.plugin_path / 'include'
        if root_include.exists():
            for h_file in root_include.glob(self.H_PATTERN):
                if '_cfg' not in h_file.name.lower() and not self._should_exclude(h_file):
                    parser = HFileParser(h_file)
                    header_files.append(parser.parse())
        
        # And root src
        root_src = self.plugin_path / 'src'
        if root_src.exists():
            for c_file in root_src.glob(self.C_PATTERN):
                if not self._should_exclude(c_file):
                    parser = CFileParser(c_file)
                    source_files.append(parser.parse())
        
        return source_files, header_files
    
    def _should_exclude(self, path: Path) -> bool:
        """Check if path should be excluded."""
        parts = path.parts
        for exclude in self.exclude_dirs:
            if exclude in parts:
                return True
        return False


# ============================================================================
# PDF DOCUMENTATION HANDLER
# ============================================================================

class PdfHandler:
    """Handle PDF documentation files."""
    
    # Common PDF locations in plugins
    PDF_PATTERNS = [
        'doc/*.pdf',
        'docs/*.pdf',
        'documentation/*.pdf',
        'manual/*.pdf',
        '*.pdf',
    ]
    
    def __init__(self, plugin_path: Path, output_path: Path):
        self.plugin_path = plugin_path
        self.output_path = output_path
        self._plugin_name = plugin_path.name
    
    def scan_pdfs(self) -> List[Dict[str, str]]:
        """Scan plugin directory for PDF files not in anchors.xml."""
        pdfs = []
        seen_names = set()
        
        for pattern in self.PDF_PATTERNS:
            for pdf_path in self.plugin_path.glob(pattern):
                if not pdf_path.is_file():
                    continue
                
                # Create unique name with plugin prefix to avoid collisions
                pdf_name = pdf_path.name
                if pdf_name in seen_names:
                    # Add plugin prefix for duplicates
                    unique_name = f"{self._plugin_name}_{pdf_name}"
                else:
                    unique_name = pdf_name
                    seen_names.add(pdf_name)
                
                pdfs.append({
                    'label': pdf_path.stem.replace('_', ' ').replace('-', ' '),
                    'href': str(pdf_path.relative_to(self.plugin_path)),
                    'local_path': '',
                    'is_scanned': True,
                    'unique_name': unique_name
                })
        
        return pdfs
    
    def copy_pdfs(self, links: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """Copy PDF files referenced in anchors.xml."""
        copied = []
        
        for link in links:
            href = link.get('href', '')
            if not href.lower().endswith('.pdf'):
                continue
            
            # Resolve relative path
            if href.startswith('doc/') or href.startswith('./doc/'):
                src_path = self.plugin_path / href.replace('./', '')
            elif href.startswith('../../'):
                src_path = self.plugin_path / href
            else:
                src_path = self.plugin_path / 'doc' / os.path.basename(href)
                if not src_path.exists():
                    src_path = self.plugin_path / href
            
            if src_path.exists() and src_path.is_file():
                try:
                    # Copy to output directory
                    dest_dir = self.output_path / 'pdf'
                    dest_dir.mkdir(parents=True, exist_ok=True)
                    
                    # Use unique name if provided, otherwise use original name
                    unique_name = link.get('unique_name', src_path.name)
                    dest_path = dest_dir / unique_name
                    
                    if not dest_path.exists():
                        shutil.copy2(src_path, dest_path)
                        logger.info(f"Copied PDF: {src_path.name} -> {unique_name}")
                    
                    # Update link reference
                    link['local_path'] = str(dest_path.relative_to(self.output_path))
                    copied.append(link)
                    
                except Exception as e:
                    logger.warning(f"Failed to copy PDF {src_path}: {e}")
        
        return copied


class PdfExtractor:
    """Extract text content from PDF files."""
    
    def __init__(self, pdf_path: Path):
        self.pdf_path = pdf_path
        self._text_cache: Optional[str] = None
        self._chapters_cache: Optional[List[Dict]] = None
    
    def extract_text(self, max_pages: int = 100) -> str:
        """Extract text from PDF, limiting to first N pages."""
        if not HAS_PYPDF2:
            return "[PDF extraction requires PyPDF2 library]"
        
        if not self.pdf_path.exists():
            return "[PDF file not found]"
        
        if self._text_cache:
            return self._text_cache
        
        try:
            reader = PdfReader(str(self.pdf_path))
            text_parts = []
            
            # Extract more pages by default
            num_pages = min(len(reader.pages), max_pages)
            
            for i in range(num_pages):
                page = reader.pages[i]
                text = page.extract_text()
                if text:
                    text_parts.append(f"### Page {i+1}\n\n{text}")
            
            self._text_cache = "\n\n".join(text_parts)
            return self._text_cache
            
        except Exception as e:
            return f"[Error extracting PDF: {e}]"
    
    def extract_all_text(self) -> str:
        """Extract full text from all pages."""
        if not HAS_PYPDF2:
            return "[PDF extraction requires PyPDF2 library]"
        
        if not self.pdf_path.exists():
            return "[PDF file not found]"
        
        try:
            reader = PdfReader(str(self.pdf_path))
            text_parts = []
            
            for i, page in enumerate(reader.pages):
                text = page.extract_text()
                if text:
                    text_parts.append(f"### Page {i+1}\n\n{text}")
            
            return "\n\n".join(text_parts)
            
        except Exception as e:
            return f"[Error extracting PDF: {e}]"
    
    def extract_chapters(self) -> List[Dict[str, Any]]:
        """Extract content organized by chapters/sections."""
        if self._chapters_cache is not None:
            return self._chapters_cache
        
        if not HAS_PYPDF2:
            return []
        
        if not self.pdf_path.exists():
            return []
        
        chapters = []
        
        try:
            reader = PdfReader(str(self.pdf_path))
            
            # Try to get TOC from PDF outlines
            if reader.outline:
                chapters = self._extract_from_outline(reader.outline)
            
            # If no TOC, try to detect chapters from text patterns
            if not chapters:
                chapters = self._detect_chapters_from_text(reader)
            
            self._chapters_cache = chapters
            return chapters
            
        except Exception as e:
            logger.debug(f"Error extracting chapters: {e}")
            return []
    
    def _extract_from_outline(self, outline: Any, level: int = 0) -> List[Dict[str, Any]]:
        """Extract chapters from PDF outline/bookmarks."""
        chapters = []
        
        def flatten_outline(items, level=0):
            for item in items:
                if isinstance(item, list):
                    flatten_outline(item, level + 1)
                else:
                    # item is a destination with title
                    title = item.title if hasattr(item, 'title') else str(item)
                    if title and title.strip():
                        chapters.append({
                            'title': title.strip(),
                            'level': level,
                            'page': None  # Would need page lookup
                        })
        
        flatten_outline(outline)
        return chapters
    
    def _detect_chapters_from_text(self, reader) -> List[Dict[str, Any]]:
        """Detect chapters from text patterns like '1. Introduction', '2. Overview', etc."""
        chapters = []
        
        # Common chapter/section patterns
        chapter_pattern = re.compile(
            r'^(\d+\.?\s+[\w\s]+|Chapter\s+\d+|Section\s+\d+)[\s.]+(.+?)$',
            re.MULTILINE
        )
        
        # Build full text to search
        full_text = ""
        for i, page in enumerate(reader.pages):
            text = page.extract_text()
            if text:
                full_text += f"\n--- Page {i+1} ---\n{text}"
        
        # Find chapter headings
        for match in chapter_pattern.finditer(full_text):
            chapter_num = match.group(1).strip()
            chapter_title = match.group(2).strip() if match.group(2) else ""
            # Find page number from context
            search_pos = match.start()
            page_marker = full_text.rfind("--- Page ", 0, search_pos)
            if page_marker != -1:
                page_end = full_text.find(" ---", page_marker)
                if page_end != -1:
                    page_info = full_text[page_marker:page_end]
                    try:
                        page_num = int(page_info.replace("--- Page ", ""))
                    except:
                        page_num = None
                else:
                    page_num = None
            else:
                page_num = None
            
            chapters.append({
                'title': f"{chapter_num} {chapter_title}".strip(),
                'level': 0,
                'page': page_num
            })
        
        return chapters
    
    def get_info(self) -> Dict[str, str]:
        """Get PDF metadata."""
        if not HAS_PYPDF2 or not self.pdf_path.exists():
            return {}
        
        try:
            reader = PdfReader(str(self.pdf_path))
            info = {
                'title': reader.metadata.get('/Title', '') if reader.metadata else '',
                'author': reader.metadata.get('/Author', '') if reader.metadata else '',
                'pages': str(len(reader.pages)),
            }
            return {k: v for k, v in info.items() if v}
        except Exception:
            return {}
    
    def extract_toc(self) -> List[Dict[str, Any]]:
        """Try to extract table of contents from PDF."""
        if not HAS_PYPDF2 or not self.pdf_path.exists():
            return []
        
        # Note: PyPDF2 has limited TOC support
        # This is a basic implementation
        return []


# ============================================================================
# MARKDOWN GENERATOR
# ============================================================================

class MarkdownGenerator:
    """Generate Markdown documentation."""
    
    def __init__(self, plugin_info: PluginInfo):
        self.plugin = plugin_info
    
    def generate(self) -> str:
        """Generate complete Markdown document."""
        lines = []
        
        # Header
        lines.extend(self._generate_header())
        
        # Overview
        lines.extend(self._generate_overview())
        
        # Version Info
        lines.extend(self._generate_version_info())
        
        # Category
        lines.extend(self._generate_category())
        
        # Documentation Links
        lines.extend(self._generate_docs())
        
        # API Reference
        lines.extend(self._generate_api_reference())
        
        # Source Files
        lines.extend(self._generate_source_files())
        
        # Extensions
        lines.extend(self._generate_extensions())
        
        # Build Targets
        lines.extend(self._generate_build_targets())
        
        # Footer
        lines.extend(self._generate_footer())
        
        return '\n'.join(lines)
    
    def _generate_header(self) -> List[str]:
        """Generate document header."""
        return [
            f"# {self.plugin.name}",
            "",
            f"**{self.plugin.module_label or 'AUTOSAR Module'}**",
            "",
            f"{self.plugin.description or self.plugin.brief or ''}",
            "",
            f"📋 Plugin Type: {self.plugin.category_type or 'MCAL Module'}",
            f"🏗️ Layer: {self.plugin.category_layer or 'MCAL'}",
            f"🎯 Target: {self.plugin.derivate or self.plugin.target or 'S32K3XX'}",
            "",
            "---",
            ""
        ]
    
    def _generate_overview(self) -> List[str]:
        """Generate module overview section."""
        lines = ["## Module Overview", ""]
        
        data = [
            ("Module ID", self.plugin.module_id),
            ("Module Label", self.plugin.module_label),
            ("Description", self.plugin.description),
            ("Peripheral", self.plugin.peripheral),
            ("Bundle Version", self.plugin.bundle_version),
            ("Bundle Vendor", self.plugin.bundle_vendor),
        ]
        
        for key, value in data:
            if value:
                lines.append(f"- **{key}:** {value}")
        
        # Handle dependencies as list
        if self.plugin.dependencies:
            lines.append(f"- **Dependencies:** {', '.join(self.plugin.dependencies[:5])}")
            if len(self.plugin.dependencies) > 5:
                lines.append(f"  (+{len(self.plugin.dependencies) - 5} more)")
        
        lines.append("")
        return lines
    
    def _generate_version_info(self) -> List[str]:
        """Generate version information section."""
        lines = ["## Version Information", ""]
        lines.append("| Property | Value |")
        lines.append("|----------|-------|")
        
        data = [
            ("Software Version", self.plugin.sw_version),
            ("Specification Version", self.plugin.spec_version),
            ("Release Version", self.plugin.rel_version),
            ("AUTOSAR Version", self.plugin.autosar_version),
            ("Build Version", self.plugin.build_version),
        ]
        
        for key, value in data:
            if value:
                lines.append(f"| {key} | {value} |")
        
        lines.append("")
        return lines
    
    def _generate_category(self) -> List[str]:
        """Generate category section."""
        if not any([self.plugin.category_type, self.plugin.category_layer,
                    self.plugin.category_category, self.plugin.category_component]):
            return []
        
        lines = ["## Category", ""]
        lines.append("| Property | Value |")
        lines.append("|----------|-------|")
        
        data = [
            ("Type", self.plugin.category_type),
            ("Layer", self.plugin.category_layer),
            ("Category", self.plugin.category_category),
            ("Component", self.plugin.category_component),
            ("Target Platform", self.plugin.target),
            ("Derivate", self.plugin.derivate),
        ]
        
        for key, value in data:
            if value:
                lines.append(f"| {key} | {value} |")
        
        lines.append("")
        return lines
    
    def _generate_docs(self) -> List[str]:
        """Generate documentation links section."""
        if not self.plugin.doc_links:
            return []
        
        lines = ["## Documentation", ""]
        
        for link in self.plugin.doc_links:
            label = link.get('label', 'Document')
            # Prefer local_path if PDF was copied
            href = link.get('local_path', '') or link.get('href', '')
            
            # Check if we generated a chapter-based markdown for this PDF
            local_path = link.get('local_path', '')
            if local_path and local_path.endswith('.pdf'):
                pdf_name = Path(local_path).stem
                md_href = f"pdf/{pdf_name}.md"
                lines.append(f"- [{label}]({md_href}) [PDF]({href})")
            elif href:
                lines.append(f"- [{label}]({href})")
            else:
                lines.append(f"- {label}")
            
            # Include short preview if PDF text was extracted
            extracted_text = link.get('extracted_text', '')
            if extracted_text and extracted_text not in ['[PDF extraction requires PyPDF2 library]', '[PDF file not found]']:
                lines.append("")
                # Show first 300 chars preview
                preview = extracted_text[:300].replace('\n', ' ').strip()
                if len(extracted_text) > 300:
                    preview += "..."
                lines.append(f"  *Quick view: {preview}*")
        
        lines.append("")
        return lines
    
    def _generate_api_reference(self) -> List[str]:
        """Generate API reference section."""
        if not self.plugin.header_files:
            return []
        
        lines = ["## API Reference", ""]
        
        for header in self.plugin.header_files:
            lines.append(f"### {header.filename}")
            lines.append("")
            
            if header.public_functions:
                for func in header.public_functions:
                    lines.extend(self._format_function(func))
                    lines.append("")
            
            if header.error_codes:
                lines.append("#### Error Codes")
                lines.append("")
                lines.append("| Name | Value | Description |")
                lines.append("|------|-------|-------------|")
                for err in header.error_codes:
                    lines.append(f"| `{err.name}` | `{err.value}` | {err.description} |")
                lines.append("")
            
            # Macros section
            if header.macros:
                lines.append("#### Macros")
                lines.append("")
                lines.append("| Name | Value |")
                lines.append("|------|-------|")
                for macro_name, macro_value in header.macros[:30]:
                    # Truncate long values
                    value_display = macro_value[:60] + "..." if len(macro_value) > 60 else macro_value
                    lines.append(f"| `{macro_name}` | `{value_display}` |")
                if len(header.macros) > 30:
                    lines.append(f"| ... | ... ({len(header.macros) - 30} more) |")
                lines.append("")
            
            # API IDs section
            if header.api_ids:
                lines.append("#### API Service IDs")
                lines.append("")
                lines.append("| Name | Value |")
                lines.append("|------|-------|")
                for api_id in header.api_ids:
                    lines.append(f"| {api_id[0]} | `{api_id[1]}` |")
                lines.append("")
            
            # Data Types section (structs, enums, typedefs)
            if header.structs or header.enums or header.typedefs:
                lines.append("#### Data Types")
                lines.append("")
                
                if header.structs:
                    lines.append("**Structures:**")
                    for struct_name, fields in header.structs[:20]:
                        lines.append(f"- `{struct_name}`: {fields}")
                    if len(header.structs) > 20:
                        lines.append(f"- ... and {len(header.structs) - 20} more structures")
                    lines.append("")
                
                if header.enums:
                    lines.append("**Enumerations:**")
                    for enum_name, values in header.enums[:20]:
                        lines.append(f"- `{enum_name}`: {values}")
                    if len(header.enums) > 20:
                        lines.append(f"- ... and {len(header.enums) - 20} more enumerations")
                    lines.append("")
                
                if header.typedefs:
                    lines.append("**Type Aliases:**")
                    for alias, original in header.typedefs[:20]:
                        lines.append(f"- `{alias}` -> `{original}`")
                    if len(header.typedefs) > 20:
                        lines.append(f"- ... and {len(header.typedefs) - 20} more type aliases")
                    lines.append("")
        
        return lines
    
    def _format_function(self, func: ApiFunction) -> List[str]:
        """Format a single function."""
        lines = [f"#### `{func.name}()`", ""]
        
        # Signature
        params_str = ", ".join(f"{p[0]} {p[1]}" for p in func.params) if func.params else "void"
        lines.append(f"```c")
        lines.append(f"{func.return_type} {func.name}({params_str});")
        lines.append(f"```")
        lines.append("")
        
        # Brief
        if func.brief:
            lines.append(f"**Brief:** {func.brief}")
            lines.append("")
        
        # Description
        if func.description:
            lines.append(f"{func.description}")
            lines.append("")
        
        # Parameters
        if func.params:
            lines.append("**Parameters:**")
            lines.append("")
            for ptype, pname in func.params:
                lines.append(f"- `{pname}` ({ptype})")
            lines.append("")
        
        # Return
        if func.return_desc:
            lines.append(f"**Returns:** {func.return_desc}")
            lines.append("")
        
        return lines
    
    def _generate_source_files(self) -> List[str]:
        """Generate source files section."""
        if not self.plugin.source_files:
            return []
        
        lines = ["## Source Files", ""]
        
        for src in self.plugin.source_files:
            lines.append(f"### {src.filename}")
            lines.append("")
            
            if src.version:
                v = src.version
                if v.sw_major:
                    lines.append(f"**Version:** {v.sw_major}.{v.sw_minor}.{v.sw_patch}")
                    lines.append("")
            
            if src.includes:
                lines.append(f"**Includes:** `{'`, `'.join(src.includes)}`")
                lines.append("")
            
            if src.functions:
                lines.append(f"**Functions:** {len(src.functions)}")
                lines.append("")
                for func in src.functions[:15]:
                    lines.append(f"- `{func.name}()` - {func.return_type}")
                if len(src.functions) > 15:
                    lines.append(f"- ... and {len(src.functions) - 15} more")
                lines.append("")
        
        return lines
    
    def _generate_extensions(self) -> List[str]:
        """Generate extensions section."""
        if not self.plugin.extensions:
            return []
        
        lines = ["## Extensions", ""]
        
        generators = [e for e in self.plugin.extensions 
                     if 'generator' in e.point.lower()]
        
        if generators:
            lines.append("### Code Generators")
            lines.append("")
            for gen in generators:
                lines.append(f"- **Class:** `{gen.generator_class}`")
                lines.append(f"  - Module ID: `{gen.module_id}`")
                if gen.modes:
                    lines.append(f"  - Modes: `{gen.modes}`")
                if gen.parameters:
                    for key, value in gen.parameters.items():
                        lines.append(f"  - {key}: `{value}`")
                lines.append("")
        
        configs = [e for e in self.plugin.extensions 
                  if 'configuration' in e.point.lower()]
        
        if configs:
            lines.append("### Configuration")
            lines.append("")
            for cfg in configs:
                if cfg.schema_resource:
                    lines.append(f"- Schema: `{cfg.schema_resource}` ({cfg.schema_type})")
            lines.append("")
        
        return lines
    
    def _generate_build_targets(self) -> List[str]:
        """Generate build targets section."""
        lines = []
        
        # Build targets
        if self.plugin.build_targets:
            lines.append("## Build Targets")
            lines.append("")
            lines.append("| Target |")
            lines.append("|--------|")
            for target in self.plugin.build_targets:
                lines.append(f"| `{target}` |")
            lines.append("")
        
        # XDM Configuration
        if self.plugin.xdm_configs:
            lines.append("## Configuration (XDM)")
            lines.append("")
            for xdm in self.plugin.xdm_configs:
                lines.append(f"### {xdm.get('filename', 'Config')}")
                lines.append("")
                
                if xdm.get('module'):
                    lines.append(f"**Module:** `{xdm['module']}`")
                    lines.append("")
                
                if xdm.get('containers'):
                    lines.append("**Containers:**")
                    lines.append("")
                    lines.append("| Container | Parameters |")
                    lines.append("|-----------|------------|")
                    for container in xdm['containers'][:20]:
                        params_str = ', '.join(f"{k}={v}" for k, v in list(container.get('parameters', {}).items())[:3])
                        if len(container.get('parameters', {})) > 3:
                            params_str += f" (+{len(container['parameters']) - 3} more)"
                        lines.append(f"| `{container['name']}` | {params_str} |")
                    if len(xdm['containers']) > 20:
                        lines.append(f"| ... | ... ({len(xdm['containers']) - 20} more) |")
                    lines.append("")
                
                if xdm.get('parameters'):
                    lines.append("**Parameters:**")
                    lines.append("")
                    lines.append("| Name | Value |")
                    lines.append("|------|-------|")
                    for param in xdm['parameters'][:20]:
                        lines.append(f"| `{param['name']}` | `{param['value']}` |")
                    if len(xdm['parameters']) > 20:
                        lines.append(f"| ... | ... |")
                    lines.append("")
        
        return lines
    
    def _generate_footer(self) -> List[str]:
        """Generate document footer."""
        return [
            "---",
            "",
            f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*",
            f"*Source: `{self.plugin.path}`*",
            ""
        ]


class IndexGenerator:
    """Generate index Markdown."""
    
    def __init__(self, plugins: List[PluginInfo]):
        self.plugins = plugins
    
    def generate(self) -> str:
        """Generate index document."""
        lines = [
            "# NXP RTD AUTOSAR Plugins Documentation",
            "",
            f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*",
            "",
            "## Overview",
            "",
            f"Documentation for {len(self.plugins)} AUTOSAR MCAL plugins from NXP RTD (R21-11) for S32K3XX platform.",
            "",
            "## Statistics",
            "",
            f"- **Total Plugins:** {len(self.plugins)}",
            f"- **Total Source Files:** {sum(len(p.source_files) for p in self.plugins)}",
            f"- **Total Header Files:** {sum(len(p.header_files) for p in self.plugins)}",
            f"- **Total API Functions:** {sum(p.api_count for p in self.plugins)}",
            "",
            "## Table of Contents",
            ""
        ]
        
        # Group by layer
        by_layer: Dict[str, List[PluginInfo]] = {}
        for plugin in sorted(self.plugins, key=lambda p: p.name):
            layer = plugin.category_layer or "Other"
            if layer not in by_layer:
                by_layer[layer] = []
            by_layer[layer].append(plugin)
        
        for layer, layer_plugins in sorted(by_layer.items()):
            lines.append(f"### {layer}")
            lines.append("")
            for plugin in layer_plugins:
                lines.append(f"- **[{plugin.name}]({plugin.name}/README.md)** - {plugin.module_label or 'N/A'}")
            lines.append("")
        
        # Summary table
        lines.extend([
            "## Plugin Summary",
            "",
            "| Plugin | Module | Version | Peripheral | Target | APIs |",
            "|--------|--------|---------|------------|--------|------|"
        ])
        
        for plugin in sorted(self.plugins, key=lambda p: p.name):
            lines.append(
                f"| {plugin.name} | {plugin.module_label or 'N/A'} | "
                f"{plugin.sw_version or 'N/A'} | {plugin.peripheral or 'N/A'} | "
                f"{plugin.derivate or 'N/A'} | {plugin.api_count} |"
            )
        
        lines.append("")
        return '\n'.join(lines)


# ============================================================================
# MAIN CONVERTER
# ============================================================================

class PluginConverter:
    """Main plugin converter class."""
    
    def __init__(self, plugins_dir: Path, output_dir: Path, extra_excludes: List[str] = None):
        self.plugins_dir = plugins_dir
        self.output_dir = output_dir
        self.extra_excludes = extra_excludes or []
        self.plugins: List[PluginInfo] = []
        self._stats = {
            'total': 0,
            'source_files': 0,
            'header_files': 0,
            'pdfs_copied': 0
        }
    
    def run(self, single_plugin: Optional[str] = None) -> None:
        """Run the conversion."""
        logger.info(f"Scanning for plugins in {self.plugins_dir}")
        
        # Find plugin directories
        plugin_dirs = []
        for item in sorted(self.plugins_dir.iterdir()):
            if item.is_dir() and (item / "plugin.xml").exists():
                if single_plugin is None or item.name == single_plugin:
                    plugin_dirs.append(item)
        
        if not plugin_dirs:
            logger.warning("No plugins found")
            return
        
        self._stats['total'] = len(plugin_dirs)
        logger.info(f"Found {len(plugin_dirs)} plugins")
        
        # Create output directory
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Process each plugin
        for plugin_dir in plugin_dirs:
            self._process_plugin(plugin_dir)
        
        # Generate index
        self._generate_index()
        
        # Print statistics
        self._print_stats()
    
    def _process_plugin(self, plugin_dir: Path) -> None:
        """Process a single plugin."""
        name = plugin_dir.name
        logger.info(f"Processing: {name}")
        
        plugin_info = PluginInfo(name=name, path=plugin_dir)
        
        # Parse XML files
        plugin_info.doc_links = AnchorsXmlParser(plugin_dir).parse()
        plugin_info.build_targets = AntGeneratorParser(plugin_dir).parse()
        
        # Parse .xdm files for Tresos configuration
        for xdm_file in plugin_dir.glob('**/*.xdm'):
            if xdm_file.is_file():
                xdm_info = XdmParser(xdm_file).parse()
                if xdm_info.get('containers') or xdm_info.get('parameters'):
                    plugin_info.xdm_configs.append(xdm_info)
        
        # Parse plugin.xml
        xml_parser = PluginXmlParser(plugin_dir)
        xml_info = xml_parser.parse()
        
        # Copy XML info to plugin_info
        for key in ['file_version', 'brief', 'project', 'platform', 'peripheral',
                    'dependencies', 'autosar_version', 'sw_version', 'build_version',
                    'copyright', 'module_id', 'module_label', 'description', 'category_type',
                    'category_layer', 'category_category', 'category_component', 'target',
                    'derivate', 'spec_version', 'rel_version', 'extensions']:
            if hasattr(xml_info, key):
                setattr(plugin_info, key, getattr(xml_info, key))
        
        # Scan source files
        scanner = SourceScanner(plugin_dir, extra_excludes=self.extra_excludes)
        source_files, header_files = scanner.scan()
        plugin_info.source_files = source_files
        plugin_info.header_files = header_files
        
        self._stats['source_files'] += len(source_files)
        self._stats['header_files'] += len(header_files)
        
        # Copy PDFs - scan first to find all PDFs, then copy
        plugin_output = self.output_dir / name
        pdf_handler = PdfHandler(plugin_dir, plugin_output)
        
        # Scan for additional PDFs not in anchors.xml
        scanned_pdfs = pdf_handler.scan_pdfs()
        for scanned_pdf in scanned_pdfs:
            # Only add if not already in doc_links (by href)
            existing_hrefs = {link.get('href', '') for link in plugin_info.doc_links}
            if scanned_pdf.get('href', '') not in existing_hrefs:
                plugin_info.doc_links.append(scanned_pdf)
        
        # Copy PDFs
        copied_pdfs = pdf_handler.copy_pdfs(plugin_info.doc_links)
        self._stats['pdfs_copied'] += len(copied_pdfs)
        
        # Extract PDF content if PyPDF2 is available
        if HAS_PYPDF2:
            pdf_dir = plugin_output / "pdf"
            for link in plugin_info.doc_links:
                local_path = link.get('local_path', '')
                if local_path and local_path.endswith('.pdf'):
                    pdf_path = plugin_output / local_path
                    if pdf_path.exists():
                        extractor = PdfExtractor(pdf_path)
                        
                        # Store preview in link for README
                        link['extracted_text'] = extractor.extract_text(max_pages=10)
                        
                        # Generate chapter-based markdown file
                        pdf_name = Path(local_path).stem  # e.g., "RTD_ZIPWIRE_UM"
                        chapters = extractor.extract_chapters()
                        
                        # Create markdown file for this PDF
                        pdf_md_path = pdf_dir / f"{pdf_name}.md"
                        pdf_md_path.parent.mkdir(parents=True, exist_ok=True)
                        
                        # Generate chapter-organized content
                        md_content = f"# {link.get('label', local_path)}\n\n"
                        md_content += f"*Source: {pdf_path.name}*\n\n"
                        
                        if chapters:
                            md_content += "## Table of Contents\n\n"
                            for ch in chapters[:30]:
                                indent = "  " * ch.get('level', 0)
                                page_info = f" (p.{ch['page']})" if ch.get('page') else ""
                                md_content += f"{indent}- [{ch['title']}](#){page_info}\n"
                            md_content += "\n---\n\n"
                        else:
                            md_content += "*No chapter structure detected in PDF.*\n\n---\n\n"
                        
                        # Extract all text and add to markdown
                        full_text = extractor.extract_all_text()
                        md_content += "## Full Content\n\n"
                        md_content += full_text
                        
                        pdf_md_path.write_text(md_content, encoding='utf-8')
                        logger.info(f"  Generated PDF doc: {pdf_md_path.name}")
        
        # Generate Markdown
        generator = MarkdownGenerator(plugin_info)
        md_content = generator.generate()
        
        # Write output
        plugin_readme = plugin_output / "README.md"
        plugin_readme.parent.mkdir(parents=True, exist_ok=True)
        plugin_readme.write_text(md_content, encoding='utf-8')
        
        self.plugins.append(plugin_info)
        
        # Log progress
        api_count = sum(len(h.public_functions) for h in header_files)
        logger.info(f"  ✓ {len(source_files)} src, {len(header_files)} hdr, {api_count} APIs")
    
    def _generate_index(self) -> None:
        """Generate index file."""
        generator = IndexGenerator(self.plugins)
        index_content = generator.generate()
        
        index_path = self.output_dir / "index.md"
        index_path.write_text(index_content, encoding='utf-8')
        logger.info(f"Generated index: {index_path}")
    
    def _print_stats(self) -> None:
        """Print conversion statistics."""
        print("\n" + "="*50)
        print("Conversion Complete")
        print("="*50)
        print(f"Total plugins: {self._stats['total']}")
        print(f"Source files:  {self._stats['source_files']}")
        print(f"Header files:  {self._stats['header_files']}")
        print(f"PDFs copied:   {self._stats['pdfs_copied']}")
        print(f"Output:        {self.output_dir}")
        print("="*50)


# ============================================================================
# CLI
# ============================================================================

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Convert NXP RTD Eclipse plugins to Markdown documentation',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python convert_plugins_to_markdown.py . -o docs
  python convert_plugins_to_markdown.py . --single Dio_TS_T40D34M30I0R0
  python convert_plugins_to_markdown.py /path/to/plugins -o output --verbose
        """
    )
    
    parser.add_argument('plugins_dir', help='Path to plugins directory')
    parser.add_argument('-o', '--output', default='docs', help='Output directory (default: docs)')
    parser.add_argument('--single', help='Process only a specific plugin')
    parser.add_argument('--exclude-dir', action='append', default=[],
                        help='Additional directories to exclude (can be specified multiple times)')
    parser.add_argument('-v', '--verbose', action='store_true', help='Enable verbose output')
    parser.add_argument('--json', help='Also export to JSON file')
    
    args = parser.parse_args()
    
    # Set logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Run converter
    plugins_dir = Path(args.plugins_dir)
    output_dir = Path(args.output)
    
    if not plugins_dir.exists():
        print(f"Error: Directory not found: {plugins_dir}")
        return 1
    
    converter = PluginConverter(plugins_dir, output_dir, extra_excludes=args.exclude_dir)
    converter.run(single_plugin=args.single)
    
    # Export to JSON if requested
    if args.json and converter.plugins:
        json_data = []
        for plugin in converter.plugins:
            # Convert to dict for JSON serialization
            plugin_dict = {
                'name': plugin.name,
                'module_id': plugin.module_id,
                'module_label': plugin.module_label,
                'description': plugin.description,
                'sw_version': plugin.sw_version,
                'autosar_version': plugin.autosar_version,
                'target': plugin.target,
                'derivate': plugin.derivate,
                'category_layer': plugin.category_layer,
                'source_files': [str(s.path) for s in plugin.source_files],
                'header_files': [str(h.path) for h in plugin.header_files],
                'api_count': plugin.api_count,
            }
            json_data.append(plugin_dict)
        
        json_path = Path(args.json)
        json_path.write_text(json.dumps(json_data, indent=2), encoding='utf-8')
        logger.info(f"Exported JSON: {json_path}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
