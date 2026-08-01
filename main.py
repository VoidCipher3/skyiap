import os
import sys
import importlib.util


BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def write_secret_file(name, secret_name):
    content = os.environ.get(secret_name)

    if not content:
        raise RuntimeError(f"{secret_name} not found")

    path = os.path.join(BASE_DIR, name)

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

    return path


def import_module(path, module_name):
    spec = importlib.util.spec_from_file_location(
        module_name,
        path
    )

    module = importlib.util.module_from_spec(spec)

    sys.modules[module_name] = module
    spec.loader.exec_module(module)

    return module


def main():

    # 生成隱藏模組
    lifecycle_path = write_secret_file(
        "lifecycle.py",
        "LIFECYCLE"
    )

    script_path = write_secret_file(
        "SCRIPT_FETCH.py",
        "SCRIPT_FETCH"
    )


    # 確保 import 可以找到 lifecycle
    sys.path.insert(0, BASE_DIR)


    # 執行 SCRIPT_FETCH
    module = import_module(
        script_path,
        "SCRIPT_FETCH"
    )

    # exec_module() only runs top-level code; the script's own
    # `if __name__ == "__main__":` guard never fires because its
    # __name__ is "SCRIPT_FETCH", not "__main__". Call main()
    # explicitly and propagate its exit code.
    if hasattr(module, "main"):
        exit_code = module.main()
        if exit_code:
            sys.exit(exit_code)


if __name__ == "__main__":
    main()
