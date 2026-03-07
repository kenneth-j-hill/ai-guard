"""Tests for the Rust parser using tree-sitter.

These tests document the behavior of Rust source code parsing.
"""

import pytest

try:
    import tree_sitter_rust
    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not TREE_SITTER_AVAILABLE,
    reason="tree-sitter-rust not installed (pip install ai-guard[rust])",
)

from ai_guard.parsers.base import get_parser_for_file
from ai_guard.parsers.rust import RustParser


class TestRustParserRegistration:
    """Tests for parser registration."""

    def test_rs_files_use_rust_parser(self):
        """RustParser is registered for .rs files."""
        parser = get_parser_for_file("test.rs")
        assert isinstance(parser, RustParser)


class TestRustParserFunctions:
    """Tests for parsing Rust functions."""

    def test_extract_simple_function(self):
        """Can extract a simple Rust function."""
        source = '''
fn add(a: i32, b: i32) -> i32 {
    a + b
}
'''
        parser = RustParser()
        ident = parser.extract_identifier(source, "add")

        assert ident is not None
        assert ident.name == "add"
        assert "fn add(a: i32, b: i32) -> i32" in ident.source
        assert "a + b" in ident.source

    def test_extract_pub_function(self):
        """Can extract a public function."""
        source = '''
pub fn greet(name: &str) -> String {
    format!("Hello, {}", name)
}
'''
        parser = RustParser()
        ident = parser.extract_identifier(source, "greet")

        assert ident is not None
        assert "pub fn greet" in ident.source

    def test_extract_async_function(self):
        """Can extract an async function."""
        source = '''
async fn fetch_data(url: &str) -> Result<String, Error> {
    let response = get(url).await?;
    Ok(response.text().await?)
}
'''
        parser = RustParser()
        ident = parser.extract_identifier(source, "fetch_data")

        assert ident is not None
        assert "async fn fetch_data" in ident.source

    def test_extract_generic_function(self):
        """Can extract a function with generics."""
        source = '''
fn maximum<T: PartialOrd>(a: T, b: T) -> T {
    if a > b { a } else { b }
}
'''
        parser = RustParser()
        ident = parser.extract_identifier(source, "maximum")

        assert ident is not None
        assert "fn maximum<T: PartialOrd>" in ident.source

    def test_extract_function_with_lifetime(self):
        """Can extract a function with lifetime annotations."""
        source = '''
fn longest<'a>(x: &'a str, y: &'a str) -> &'a str {
    if x.len() > y.len() { x } else { y }
}
'''
        parser = RustParser()
        ident = parser.extract_identifier(source, "longest")

        assert ident is not None
        assert "fn longest<'a>" in ident.source

    def test_extract_unsafe_function(self):
        """Can extract an unsafe function."""
        source = '''
unsafe fn dangerous() {
    // unsafe code here
}
'''
        parser = RustParser()
        ident = parser.extract_identifier(source, "dangerous")

        assert ident is not None
        assert "unsafe fn dangerous" in ident.source

    def test_function_body_change_changes_hash(self, temp_project):
        """Changing function body changes the hash."""
        from ai_guard.core import GuardFile

        source1 = '''
fn calculate(x: i32) -> i32 {
    x * 2
}
'''
        source2 = '''
fn calculate(x: i32) -> i32 {
    x * 3
}
'''
        filepath = temp_project / "math.rs"
        filepath.write_text(source1)

        guard = GuardFile(temp_project)
        guard.add_identifier("math.rs", "calculate")
        hash1 = guard.entries[0].hash

        filepath.write_text(source2)
        guard2 = GuardFile(temp_project)
        guard2.add_identifier("math.rs", "calculate")
        hash2 = guard2.entries[0].hash

        assert hash1 != hash2


class TestRustParserStructs:
    """Tests for parsing Rust structs."""

    def test_extract_simple_struct(self):
        """Can extract a simple struct."""
        source = '''
struct Point {
    x: f64,
    y: f64,
}
'''
        parser = RustParser()
        ident = parser.extract_identifier(source, "Point")

        assert ident is not None
        assert ident.name == "Point"
        assert "struct Point" in ident.source
        assert "x: f64" in ident.source
        assert "y: f64" in ident.source

    def test_extract_pub_struct(self):
        """Can extract a public struct with pub fields."""
        source = '''
pub struct Config {
    pub max_size: usize,
    pub name: String,
}
'''
        parser = RustParser()
        ident = parser.extract_identifier(source, "Config")

        assert ident is not None
        assert "pub struct Config" in ident.source

    def test_extract_generic_struct(self):
        """Can extract a struct with generics."""
        source = '''
struct Wrapper<T> {
    inner: T,
}
'''
        parser = RustParser()
        ident = parser.extract_identifier(source, "Wrapper")

        assert ident is not None
        assert "struct Wrapper<T>" in ident.source


class TestRustParserEnums:
    """Tests for parsing Rust enums."""

    def test_extract_simple_enum(self):
        """Can extract a simple enum."""
        source = '''
enum Color {
    Red,
    Green,
    Blue,
}
'''
        parser = RustParser()
        ident = parser.extract_identifier(source, "Color")

        assert ident is not None
        assert "enum Color" in ident.source
        assert "Red" in ident.source
        assert "Green" in ident.source

    def test_extract_enum_with_data(self):
        """Can extract an enum with associated data."""
        source = '''
enum Shape {
    Circle(f64),
    Rectangle(f64, f64),
    Point { x: f64, y: f64 },
}
'''
        parser = RustParser()
        ident = parser.extract_identifier(source, "Shape")

        assert ident is not None
        assert "Circle(f64)" in ident.source
        assert "Rectangle(f64, f64)" in ident.source


class TestRustParserTraits:
    """Tests for parsing Rust traits."""

    def test_extract_trait(self):
        """Can extract a trait definition."""
        source = '''
trait Drawable {
    fn draw(&self);
    fn area(&self) -> f64;
}
'''
        parser = RustParser()
        ident = parser.extract_identifier(source, "Drawable")

        assert ident is not None
        assert "trait Drawable" in ident.source
        assert "fn draw(&self)" in ident.source
        assert "fn area(&self) -> f64" in ident.source


class TestRustParserImpl:
    """Tests for parsing Rust impl blocks."""

    def test_extract_impl_block(self):
        """Can extract an impl block by its type name."""
        source = '''
struct Point {
    x: f64,
    y: f64,
}

impl Point {
    fn new(x: f64, y: f64) -> Self {
        Point { x, y }
    }
}
'''
        parser = RustParser()
        ident = parser.extract_identifier(source, "Point")

        # Should match the struct, not the impl
        assert ident is not None
        assert "struct Point" in ident.source


class TestRustParserConsts:
    """Tests for parsing Rust constants and statics."""

    def test_extract_const(self):
        """Can extract a const item."""
        source = '''
const MAX_SIZE: usize = 1024;
'''
        parser = RustParser()
        ident = parser.extract_identifier(source, "MAX_SIZE")

        assert ident is not None
        assert "const MAX_SIZE: usize = 1024;" in ident.source

    def test_extract_static(self):
        """Can extract a static item."""
        source = '''
static COUNTER: i32 = 0;
'''
        parser = RustParser()
        ident = parser.extract_identifier(source, "COUNTER")

        assert ident is not None
        assert "static COUNTER: i32 = 0;" in ident.source


class TestRustParserTypeAlias:
    """Tests for parsing Rust type aliases."""

    def test_extract_type_alias(self):
        """Can extract a type alias."""
        source = '''
type Pair = (i32, i32);
'''
        parser = RustParser()
        ident = parser.extract_identifier(source, "Pair")

        assert ident is not None
        assert "type Pair = (i32, i32);" in ident.source


class TestRustParserMacros:
    """Tests for parsing Rust macros."""

    def test_extract_macro_definition(self):
        """Can extract a macro_rules! definition."""
        source = '''
macro_rules! say_hello {
    () => {
        println!("Hello!");
    };
}
'''
        parser = RustParser()
        ident = parser.extract_identifier(source, "say_hello")

        assert ident is not None
        assert "macro_rules! say_hello" in ident.source


class TestRustParserModules:
    """Tests for parsing Rust modules."""

    def test_extract_module(self):
        """Can extract a mod block."""
        source = '''
mod utils {
    pub fn helper() -> bool {
        true
    }
}
'''
        parser = RustParser()
        ident = parser.extract_identifier(source, "utils")

        assert ident is not None
        assert "mod utils" in ident.source
        assert "fn helper()" in ident.source


class TestRustParserListIdentifiers:
    """Tests for listing all identifiers."""

    def test_list_all_identifiers(self):
        """Can list all top-level identifiers in a Rust file."""
        source = '''
const MAX: usize = 100;

struct Buffer {
    data: Vec<u8>,
}

impl Buffer {
    fn new() -> Self {
        Buffer { data: Vec::new() }
    }
}

fn process(buf: &Buffer) -> bool {
    !buf.data.is_empty()
}
'''
        parser = RustParser()
        identifiers = parser.list_identifiers(source)

        names = {i.name for i in identifiers}
        assert "MAX" in names
        assert "Buffer" in names
        assert "process" in names
        # impl block is named by its type
        assert "Buffer" in names


class TestRustParserMembers:
    """Tests for parsing struct fields and impl methods using :: notation."""

    def test_extract_struct_field(self):
        """Can extract a struct field using :: notation."""
        source = '''
struct Point {
    x: f64,
    y: f64,
}
'''
        parser = RustParser()
        ident = parser.extract_identifier(source, "Point::x")

        assert ident is not None
        assert ident.name == "Point::x"
        assert "x: f64" in ident.source

    def test_extract_impl_method(self):
        """Can extract an impl method using :: notation."""
        source = '''
struct Point {
    x: f64,
    y: f64,
}

impl Point {
    fn new(x: f64, y: f64) -> Self {
        Point { x, y }
    }

    fn distance(&self) -> f64 {
        (self.x * self.x + self.y * self.y).sqrt()
    }
}
'''
        parser = RustParser()
        ident = parser.extract_identifier(source, "Point::distance")

        assert ident is not None
        assert ident.name == "Point::distance"
        assert "fn distance(&self) -> f64" in ident.source

    def test_list_struct_fields(self):
        """Can list all fields of a struct."""
        source = '''
struct Rectangle {
    width: f64,
    height: f64,
}
'''
        parser = RustParser()
        members = parser.expand_identifier_pattern(source, "Rectangle::*")

        names = {m.name for m in members}
        assert "Rectangle::width" in names
        assert "Rectangle::height" in names

    def test_list_impl_methods(self):
        """Can list methods from an impl block."""
        source = '''
struct Calculator;

impl Calculator {
    fn add(a: i32, b: i32) -> i32 { a + b }
    fn subtract(a: i32, b: i32) -> i32 { a - b }
}
'''
        parser = RustParser()
        members = parser.expand_identifier_pattern(source, "Calculator::*")

        names = {m.name for m in members}
        assert "Calculator::add" in names
        assert "Calculator::subtract" in names

    def test_list_combined_fields_and_methods(self):
        """Wildcard lists both struct fields and impl methods."""
        source = '''
struct Config {
    max_size: usize,
    name: String,
}

impl Config {
    fn new(name: String) -> Self {
        Config { max_size: 100, name }
    }
}
'''
        parser = RustParser()
        members = parser.expand_identifier_pattern(source, "Config::*")

        names = {m.name for m in members}
        assert "Config::max_size" in names
        assert "Config::name" in names
        assert "Config::new" in names

    def test_wildcard_filter_members(self):
        """Wildcard pattern filters members."""
        source = '''
struct Config {
    max_size: usize,
    max_count: usize,
    name: String,
}
'''
        parser = RustParser()
        members = parser.expand_identifier_pattern(source, "Config::max_*")

        names = {m.name for m in members}
        assert "Config::max_size" in names
        assert "Config::max_count" in names
        assert "Config::name" not in names

    def test_extract_enum_variant(self):
        """Can extract an enum variant using :: notation."""
        source = '''
enum Color {
    Red,
    Green,
    Blue,
}
'''
        parser = RustParser()
        ident = parser.extract_identifier(source, "Color::Red")

        assert ident is not None
        assert ident.name == "Color::Red"

    def test_list_enum_variants(self):
        """Can list all variants of an enum."""
        source = '''
enum Direction {
    North,
    South,
    East,
    West,
}
'''
        parser = RustParser()
        members = parser.expand_identifier_pattern(source, "Direction::*")

        names = {m.name for m in members}
        assert "Direction::North" in names
        assert "Direction::South" in names
        assert "Direction::East" in names
        assert "Direction::West" in names

    def test_nonexistent_member_returns_none(self):
        """Returns None for nonexistent members."""
        source = '''
struct Point {
    x: f64,
}
'''
        parser = RustParser()
        result = parser.extract_identifier(source, "Point::z")
        assert result is None

    def test_nonexistent_type_returns_none(self):
        """Returns None for nonexistent type members."""
        source = '''
struct Point {
    x: f64,
}
'''
        parser = RustParser()
        result = parser.extract_identifier(source, "NonExistent::x")
        assert result is None

    def test_member_hash_changes_on_modification(self, temp_project):
        """Changing a member changes its hash."""
        from ai_guard.core import GuardFile

        source1 = '''
struct Config {
    max_size: usize,
}
'''
        source2 = '''
struct Config {
    max_size: u64,
}
'''
        filepath = temp_project / "config.rs"
        filepath.write_text(source1)

        guard = GuardFile(temp_project)
        guard.add_identifier("config.rs", "Config::max_size")
        hash1 = guard.entries[0].hash

        filepath.write_text(source2)
        guard2 = GuardFile(temp_project)
        guard2.add_identifier("config.rs", "Config::max_size")
        hash2 = guard2.entries[0].hash

        assert hash1 != hash2

    def test_verify_changed_member_fails(self, temp_project):
        """Verification fails when a protected member has been modified."""
        from ai_guard.core import GuardFile

        source1 = '''
impl Point {
    fn distance(&self) -> f64 {
        (self.x * self.x + self.y * self.y).sqrt()
    }
}
'''
        source2 = '''
impl Point {
    fn distance(&self) -> f64 {
        (self.x.powi(2) + self.y.powi(2)).sqrt()
    }
}
'''
        filepath = temp_project / "point.rs"
        filepath.write_text(source1)

        guard = GuardFile(temp_project)
        guard.add_identifier("point.rs", "Point::distance")
        guard.save()

        filepath.write_text(source2)

        guard2 = GuardFile(temp_project)
        failures = guard2.verify()
        member_failures = [(e, r) for e, r in failures if e.identifier is not None]
        assert len(member_failures) == 1
        assert member_failures[0][0].identifier == "Point::distance"
        assert member_failures[0][1] == "hash mismatch"


class TestRustParserEdgeCases:
    """Tests for edge cases and error handling."""

    def test_nonexistent_identifier_returns_none(self):
        """Returns None for nonexistent identifiers."""
        source = "fn main() {}"
        parser = RustParser()
        result = parser.extract_identifier(source, "nonexistent")
        assert result is None

    def test_empty_source_returns_empty_list(self):
        """Empty source returns empty identifier list."""
        parser = RustParser()
        identifiers = parser.list_identifiers("")
        assert identifiers == []

    def test_identifier_includes_line_numbers(self):
        """Extracted identifiers include line number information."""
        source = '''// Comment
// Another comment

fn my_function() -> bool {
    true
}
'''
        parser = RustParser()
        ident = parser.extract_identifier(source, "my_function")

        assert ident is not None
        assert ident.start_line == 4
        assert ident.end_line == 6

    def test_handles_where_clause(self):
        """Can handle functions with where clauses."""
        source = '''
fn process<T>(item: T) -> String
where
    T: std::fmt::Display,
{
    format!("{}", item)
}
'''
        parser = RustParser()
        ident = parser.extract_identifier(source, "process")

        assert ident is not None
        assert "where" in ident.source
        assert "T: std::fmt::Display" in ident.source

    def test_handles_attribute_macros(self):
        """Can handle functions with attribute macros."""
        source = '''
#[derive(Debug)]
struct MyStruct {
    value: i32,
}
'''
        parser = RustParser()
        ident = parser.extract_identifier(source, "MyStruct")

        assert ident is not None
        assert "struct MyStruct" in ident.source
