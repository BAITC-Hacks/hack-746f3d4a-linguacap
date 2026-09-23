from app.diarization import SpeakerTurn, normalize_speaker_turns, speaker_for_interval


def test_turns_are_given_neutral_stable_ids_and_adjacent_turns_merge():
    turns = normalize_speaker_turns(
        [
            SpeakerTurn("raw-b", 5.0, 7.0),
            SpeakerTurn("raw-a", 0.0, 2.0),
            SpeakerTurn("raw-a", 2.1, 4.0),
        ]
    )

    assert turns == (
        SpeakerTurn("SPEAKER_01", 0.0, 4.0),
        SpeakerTurn("SPEAKER_02", 5.0, 7.0),
    )


def test_speaker_is_assigned_by_largest_timestamp_overlap():
    turns = (
        SpeakerTurn("SPEAKER_01", 0.0, 3.0),
        SpeakerTurn("SPEAKER_02", 3.0, 9.0),
    )

    assert speaker_for_interval(2.0, 6.0, turns) == "SPEAKER_02"
    assert speaker_for_interval(10.0, 11.0, turns) is None
