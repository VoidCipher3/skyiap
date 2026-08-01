import os
import sys
import importlib.util


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.join(BASE_DIR, "scripts")


def write_secret_file(name, secret_name, target_dir=BASE_DIR):
    content = os.environ.get(secret_name)

    if not content:
        raise RuntimeError(f"{secret_name} not found")

    os.makedirs(target_dir, exist_ok=True)
    path = os.path.join(target_dir, name)

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

    # 生成隱藏模組（放進 scripts/，對齊 SCRIPT_FETCH 內部
    # HERE = dirname(__file__) / ROOT = dirname(HERE) 的路徑假設，
    # 否則 ROOT 會多算一層，data/ 被寫到 repo 外面）
    lifecycle_path = write_secret_file(
        "lifecycle.py",
        "LIFECYCLE",
        target_dir=SCRIPTS_DIR
    )

    script_path = write_secret_file(
        "SCRIPT_FETCH.py",
        "SCRIPT_FETCH",
        target_dir=SCRIPTS_DIR
    )


    # 確保 import 可以找到 lifecycle（現在跟 SCRIPT_FETCH 同一層）
    sys.path.insert(0, SCRIPTS_DIR)


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
