"""Tests for the GCC/G++ parsers.

These tests document the behavior of C and C++ parsing using the GCC toolchain.
"""

import shutil

import pytest

from ai_guard.parsers.gcc import GCCParser, GPPParser


# Check if GCC is available on this system
GCC_AVAILABLE = shutil.which("gcc") is not None
from ai_guard.parsers.base import get_parser_for_file


class TestGCCParserRegistration:
    """Tests for parser registration."""

    def test_c_files_use_gcc_parser(self):
        """GCCParser is registered for .c files."""
        parser = get_parser_for_file("test.c")
        assert isinstance(parser, GCCParser)

    def test_h_files_use_gcc_parser(self):
        """GCCParser is registered for .h files."""
        parser = get_parser_for_file("test.h")
        assert isinstance(parser, GCCParser)

    def test_cpp_files_use_gpp_parser(self):
        """GPPParser is registered for .cpp files."""
        parser = get_parser_for_file("test.cpp")
        assert isinstance(parser, GPPParser)

    def test_hpp_files_use_gpp_parser(self):
        """GPPParser is registered for .hpp files."""
        parser = get_parser_for_file("test.hpp")
        assert isinstance(parser, GPPParser)

    def test_cc_files_use_gpp_parser(self):
        """GPPParser is registered for .cc files."""
        parser = get_parser_for_file("test.cc")
        assert isinstance(parser, GPPParser)


class TestGCCParserFunctions:
    """Tests for parsing C functions."""

    def test_extract_simple_function(self):
        """Can extract a simple C function."""
        source = '''
int add(int a, int b) {
    return a + b;
}
'''
        parser = GCCParser()
        ident = parser.extract_identifier(source, "add")

        assert ident is not None
        assert ident.name == "add"
        assert "int add(int a, int b)" in ident.source
        assert "return a + b;" in ident.source

    def test_extract_void_function(self):
        """Can extract a void function."""
        source = '''
void do_nothing(void) {
    return;
}
'''
        parser = GCCParser()
        ident = parser.extract_identifier(source, "do_nothing")

        assert ident is not None
        assert ident.name == "do_nothing"
        assert "void do_nothing(void)" in ident.source

    def test_extract_static_function(self):
        """Can extract a static function."""
        source = '''
static int helper(int x) {
    return x * 2;
}
'''
        parser = GCCParser()
        ident = parser.extract_identifier(source, "helper")

        assert ident is not None
        assert "static int helper" in ident.source

    def test_extract_function_with_pointers(self):
        """Can extract a function returning a pointer."""
        source = '''
char *get_string(void) {
    return "hello";
}
'''
        parser = GCCParser()
        ident = parser.extract_identifier(source, "get_string")

        assert ident is not None
        assert "char *get_string" in ident.source

    def test_extract_function_with_nested_braces(self):
        """Correctly handles nested braces in function body."""
        source = '''
int complex(int x) {
    if (x > 0) {
        for (int i = 0; i < x; i++) {
            if (i % 2 == 0) {
                x++;
            }
        }
    }
    return x;
}
'''
        parser = GCCParser()
        ident = parser.extract_identifier(source, "complex")

        assert ident is not None
        assert "return x;" in ident.source

    def test_function_body_change_changes_hash(self, temp_project):
        """Changing function body changes the hash."""
        from ai_guard.core import GuardFile

        source1 = '''
int calculate(int x) {
    return x * 2;
}
'''
        source2 = '''
int calculate(int x) {
    return x * 3;
}
'''
        filepath = temp_project / "math.c"
        filepath.write_text(source1)

        guard = GuardFile(temp_project)
        guard.add_identifier("math.c", "calculate")
        hash1 = guard.entries[0].hash

        filepath.write_text(source2)
        guard2 = GuardFile(temp_project)
        guard2.add_identifier("math.c", "calculate")
        hash2 = guard2.entries[0].hash

        assert hash1 != hash2


class TestGCCParserStructs:
    """Tests for parsing C structs."""

    def test_extract_simple_struct(self):
        """Can extract a simple struct."""
        source = '''
struct Point {
    int x;
    int y;
};
'''
        parser = GCCParser()
        ident = parser.extract_identifier(source, "Point")

        assert ident is not None
        assert ident.name == "Point"
        assert "struct Point" in ident.source
        assert "int x;" in ident.source
        assert "int y;" in ident.source

    def test_extract_struct_with_functions(self):
        """Can extract a struct containing function pointers."""
        source = '''
struct Callbacks {
    void (*on_start)(void);
    int (*on_data)(char *buf, int len);
    void (*on_end)(void);
};
'''
        parser = GCCParser()
        ident = parser.extract_identifier(source, "Callbacks")

        assert ident is not None
        assert "void (*on_start)" in ident.source

    def test_extract_union(self):
        """Can extract a union."""
        source = '''
union Value {
    int i;
    float f;
    char *s;
};
'''
        parser = GCCParser()
        ident = parser.extract_identifier(source, "Value")

        assert ident is not None
        assert "union Value" in ident.source

    def test_extract_enum(self):
        """Can extract an enum."""
        source = '''
enum Color {
    RED,
    GREEN,
    BLUE
};
'''
        parser = GCCParser()
        ident = parser.extract_identifier(source, "Color")

        assert ident is not None
        assert "enum Color" in ident.source
        assert "RED" in ident.source


class TestGCCParserMacros:
    """Tests for parsing C macros."""

    def test_extract_simple_macro(self):
        """Can extract a simple #define macro."""
        source = '''
#define MAX_SIZE 1024
'''
        parser = GCCParser()
        ident = parser.extract_identifier(source, "MAX_SIZE")

        assert ident is not None
        assert "#define MAX_SIZE 1024" in ident.source

    def test_extract_function_macro(self):
        """Can extract a function-like macro."""
        source = '''
#define MAX(a, b) ((a) > (b) ? (a) : (b))
'''
        parser = GCCParser()
        ident = parser.extract_identifier(source, "MAX")

        assert ident is not None
        assert "#define MAX(a, b)" in ident.source

    def test_extract_multiline_macro(self):
        """Can extract a multiline macro with continuations."""
        source = '''
#define MULTILINE_MACRO(x) \\
    do { \\
        printf("%d\\n", x); \\
    } while(0)
'''
        parser = GCCParser()
        ident = parser.extract_identifier(source, "MULTILINE_MACRO")

        assert ident is not None
        assert "do {" in ident.source or "do { \\" in ident.source


class TestGCCParserGlobalVars:
    """Tests for parsing global variables."""

    def test_extract_global_variable(self):
        """Can extract a global variable."""
        source = '''
int global_counter = 0;
'''
        parser = GCCParser()
        ident = parser.extract_identifier(source, "global_counter")

        assert ident is not None
        assert "int global_counter = 0;" in ident.source

    def test_extract_static_global(self):
        """Can extract a static global variable."""
        source = '''
static const char *version = "1.0.0";
'''
        parser = GCCParser()
        ident = parser.extract_identifier(source, "version")

        assert ident is not None
        assert 'static const char *version' in ident.source


class TestGCCParserListIdentifiers:
    """Tests for listing all identifiers."""

    def test_list_all_identifiers(self):
        """Can list all top-level identifiers in a C file."""
        source = '''
#define BUFFER_SIZE 256

struct Buffer {
    char data[BUFFER_SIZE];
    int len;
};

static int count = 0;

void init_buffer(struct Buffer *buf) {
    buf->len = 0;
}

int get_count(void) {
    return count;
}
'''
        parser = GCCParser()
        identifiers = parser.list_identifiers(source)

        names = {i.name for i in identifiers}
        assert "BUFFER_SIZE" in names
        assert "Buffer" in names
        assert "init_buffer" in names
        assert "get_count" in names


class TestGPPParserCppFeatures:
    """Tests for C++ specific features."""

    def test_extract_class(self):
        """Can extract a C++ class."""
        source = '''
class Rectangle {
public:
    Rectangle(int w, int h) : width(w), height(h) {}
    int area() const { return width * height; }

private:
    int width;
    int height;
};
'''
        parser = GPPParser()
        ident = parser.extract_identifier(source, "Rectangle")

        assert ident is not None
        assert "class Rectangle" in ident.source
        assert "int area()" in ident.source

    def test_extract_class_with_inheritance(self):
        """Can extract a class with inheritance."""
        source = '''
class Derived : public Base {
public:
    void method() override {
        Base::method();
    }
};
'''
        parser = GPPParser()
        ident = parser.extract_identifier(source, "Derived")

        assert ident is not None
        assert "class Derived : public Base" in ident.source

    def test_extract_template_function(self):
        """Can extract a template function."""
        source = '''
template<typename T>
T maximum(T a, T b) {
    return (a > b) ? a : b;
}
'''
        parser = GPPParser()
        ident = parser.extract_identifier(source, "maximum")

        assert ident is not None
        assert "return (a > b)" in ident.source

    def test_extract_namespace_function(self):
        """Can extract a function that might be in a namespace."""
        source = '''
namespace utils {

int helper(int x) {
    return x * 2;
}

}
'''
        parser = GPPParser()
        ident = parser.extract_identifier(source, "helper")

        assert ident is not None
        assert "int helper(int x)" in ident.source


class TestGCCParserEdgeCases:
    """Tests for edge cases and error handling."""

    def test_nonexistent_identifier_returns_none(self):
        """Returns None for nonexistent identifiers."""
        source = "int x = 1;"
        parser = GCCParser()

        result = parser.extract_identifier(source, "nonexistent")
        assert result is None

    def test_handles_comments_in_functions(self):
        """Correctly handles comments containing braces."""
        source = '''
int tricky(int x) {
    // This { brace } shouldn't confuse the parser
    /* Neither should { this } */
    return x;
}
'''
        parser = GCCParser()
        ident = parser.extract_identifier(source, "tricky")

        assert ident is not None
        assert "return x;" in ident.source

    def test_handles_strings_with_braces(self):
        """Correctly handles strings containing braces."""
        source = '''
void print_json(void) {
    printf("{ \\"key\\": \\"value\\" }");
}
'''
        parser = GCCParser()
        ident = parser.extract_identifier(source, "print_json")

        assert ident is not None
        assert 'printf' in ident.source

    def test_empty_source_returns_empty_list(self):
        """Empty source returns empty identifier list."""
        parser = GCCParser()
        identifiers = parser.list_identifiers("")

        assert identifiers == []

    @pytest.mark.skipif(not GCC_AVAILABLE, reason="GCC not installed")
    def test_syntax_check_valid_code(self):
        """Syntax check passes for valid C code."""
        source = '''
int main(void) {
    return 0;
}
'''
        parser = GCCParser()
        assert parser.check_syntax(source) is True

    @pytest.mark.skipif(not GCC_AVAILABLE, reason="GCC not installed")
    def test_syntax_check_invalid_code(self):
        """Syntax check fails for invalid C code."""
        source = '''
int main(void) {
    return  // missing semicolon and value
}
'''
        parser = GCCParser()
        assert parser.check_syntax(source) is False
