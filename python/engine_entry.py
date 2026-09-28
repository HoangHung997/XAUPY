import multiprocessing


if __name__ == "__main__":
    multiprocessing.freeze_support()
    from xaupy_engine.main import main
    raise SystemExit(main())
