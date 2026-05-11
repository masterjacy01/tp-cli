from tp_cli.client import _total_duration_from_structure, build_structure, search_exercises


def test_build_structure_sets_metric_by_sport_and_duration():
    structure = build_structure(
        [
            {"type": "warmup", "duration": 600, "start": 50, "end": 75},
            {
                "type": "intervals",
                "repeat": 3,
                "on_duration": 300,
                "off_duration": 120,
                "on_target": 95,
                "off_target": 55,
            },
            {"type": "cooldown", "duration": 300, "start": 65, "end": 45},
        ],
        sport="run",
    )

    assert structure["primaryIntensityMetric"] == "percentOfThresholdHr"
    assert structure["primaryLengthMetric"] == "duration"
    assert _total_duration_from_structure(structure) == 2160


def test_search_exercises_uses_bundled_catalog():
    results = search_exercises("plank", limit=5)

    assert results
    assert len(results) <= 5
    assert all("plank" in item["title"].lower() for item in results)
