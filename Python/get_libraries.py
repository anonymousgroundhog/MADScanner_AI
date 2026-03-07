import ast
import os
import sys

def get_imports_from_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        try:
            tree = ast.parse(f.read())
        except SyntaxError:
            return set()

    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for n in node.names:
                imports.add(n.name.split('.')[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.add(node.module.split('.')[0])
    return imports

def main():
    all_libraries = set()
    # Standard library list to ignore (partial list for example)
    stdlib = sys.builtin_module_names
    
    for filename in os.listdir('.'):
        if filename.endswith('.py'):
            libs = get_imports_from_file(filename)
            all_libraries.update(libs)
    
    # Filter out common built-ins and print
    external_libs = [lib for lib in all_libraries if lib not in stdlib]
    print("\n".join(sorted(external_libs)))

if __name__ == "__main__":
    main()
