from pathlib import Path

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]


def test_game_first_selection_persists_and_prevents_duplicate_identity():
    app = AppTest.from_file(ROOT / "app_v6_preview.py").run(timeout=20)
    assert len(app.selectbox) == 1
    first_game, second_game = app.selectbox[0].options[:2]

    app.selectbox[0].set_value(first_game).run(timeout=20)
    add_buttons = [button for button in app.button if str(button.key).startswith("add_")]
    assert add_buttons
    selected_id = str(add_buttons[0].key).removeprefix("add_")
    add_buttons[0].click().run(timeout=20)
    assert selected_id in app.session_state["v6_selected_ids"]

    selected_button = next(button for button in app.button if button.key == f"add_{selected_id}")
    assert not selected_button.disabled
    assert selected_button.label == "♥"
    assert next(button for button in app.button if button.key == f"remove_{selected_id}")

    app.selectbox[0].set_value(second_game).run(timeout=20)
    assert selected_id in app.session_state["v6_selected_ids"]
    visible_add_ids = {
        str(button.key).removeprefix("add_")
        for button in app.button
        if str(button.key).startswith("add_")
    }
    assert selected_id not in visible_add_ids


def test_select_search_surface_is_forced_to_light_theme():
    source = (ROOT / "app_v6_preview.py").read_text(encoding="utf-8")
    assert '[data-testid="stSelectbox"] input' in source
    assert '[data-baseweb="popover"]' in source
    assert "background-color: #fffefe !important" in source
    assert "-webkit-text-fill-color: #443941 !important" in source
    assert 'key=f"remove_{character_id}", type="secondary"' in source
    assert 'type="primary" if selected_already' not in source
    assert '<div class="v6-full-name">AOtomeMatch</div>' in source
