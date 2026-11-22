"""Checkpoint defaults per robot: cell fine-tunes stay cell-scoped (they forget the banana, 22.11.)."""

from app.robots import active_checkpoint


def test_cell_finetune_is_not_the_default_for_other_skills() -> None:
    jobs = {
        "a": {"robot": "yam-sim", "dataset": "pickup-v1", "fine_tuned_model": "ft-general", "finished_at": "1"},
        "b": {"robot": "yam-sim", "dataset": "cells-v1", "fine_tuned_model": "ft-cells", "finished_at": "2"},
        "c": {"robot": "yam-sim", "dataset": "cells-v1", "fine_tuned_model": None, "finished_at": "3"},
    }
    assert active_checkpoint("yam-sim", jobs) == "ft-general"  # newer cell fine-tune ignored
    assert active_checkpoint("yam-sim", jobs, cells=True) == "ft-cells"
    assert active_checkpoint("yam-sim", {k: v for k, v in jobs.items() if k != "a"}) is None  # base model
