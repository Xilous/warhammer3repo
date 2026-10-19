from assist import turnstate as T


def test_new_turn_or_campaign_drops_what_the_old_owed(tmp_path, monkeypatch):
    monkeypatch.setattr(T, "PATH", tmp_path / "turn_state.json")
    st = T.for_turn(T.TurnState(), "0x1:clan", 5)
    st.end_requested = True
    T.save(st)
    assert T.for_turn(T.load(), "0x1:clan", 5).end_requested          # same turn: kept across a restart
    assert not T.for_turn(T.load(), "0x1:clan", 6).end_requested      # next turn: dropped
    assert not T.for_turn(T.load(), "0x2:clan", 5).end_requested      # another campaign: dropped


def test_owes_end_before_run_and_nothing_once_ended():
    st = T.TurnState(campaign="c", turn=3, end_requested=True, run_requested=True)
    assert st.owes() == ["end"]                  # Build & End Turn runs the turn-start steps too
    st.end_done = True
    assert st.owes() == ["run"]
    st.run_requested = False
    assert st.owes() == []


def test_campaign_id():
    assert T.campaign_id(0x1A, "wh3_dlc29_skv_clan_scruten") == "0x1a:wh3_dlc29_skv_clan_scruten"
    assert T.campaign_id(None, "x") == ""
