import logging

from cal_sync.logging_config import configure_logging


def test_configure_logging_overwrites_existing_log_file(tmp_path):
    log_path = tmp_path / "sync.log"
    log_path.write_text("old run\n", encoding="utf-8")

    configure_logging(log_path)
    logging.getLogger("test").info("new run")
    logging.shutdown()

    log_text = log_path.read_text(encoding="utf-8")
    assert "new run" in log_text
    assert "old run" not in log_text
