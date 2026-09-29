"""DST app shell: branding, sidebar, top-bar actions, the language menu.

Same shape as the NiD4OCEAN DST shell. The brand theme is `www/seagarden.css`, inlined
into the page so it needs no static route and survives the sub-path proxy and an
offline host. The two logo PNGs are base64-inlined for the same reason: a broken image
link degrades silently to an empty box, and the funding lockup is one Interreg's
communication rules require to be visible.

Every string here comes from the session's `Translator` (package I). The old `t()`
passthrough is gone: `tr("app.shell.assess")` looks the key up in the language the
request asked for, and the pseudo-locale test in app/tests/test_i18n_leaks.py fails
on any literal that slips past it.
"""

from __future__ import annotations

import base64
from collections.abc import Sequence
from pathlib import Path

from shiny import ui

from app.i18n import LANGUAGE_NAMES, Translator, english

_WWW = Path(__file__).parent / "www"
_BRAND_CSS = _WWW / "seagarden.css"
_ICON = _WWW / "seagarden-icon.png"  # the circular mark, from the Communication folder
_FUNDING = _WWW / "seagarden-funding-lockup.png"  # SeaGarden | Interreg South Baltic | EU

REPO_URL = "https://github.com/razinkele/seagarden-dst"
CONTACT_EMAIL = "arturas.razinkovas-baziukas@ku.lt"


def _data_uri(path: Path) -> str:
    """Base64-inline a PNG so the page needs no static-asset route for it."""
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def _brand() -> ui.Tag:
    """Navbar brand: the circular icon mark, the name with the lime 'Sea', a DST tag.
    Proper nouns, not translated."""
    return ui.tags.span(
        ui.tags.img(src=_data_uri(_ICON), class_="sg-logo", alt=""),
        ui.tags.span(ui.tags.b("Sea"), "Garden", class_="sg-name"),
        ui.tags.span("DST", class_="sg-dst"),
        class_="sg-brand",
    )


def _funding_strip(tr: Translator) -> ui.Tag:
    """The full lockup on a white strip: it is dark-on-white and cannot sit in the bar."""
    return ui.div(
        ui.tags.img(
            src=_data_uri(_FUNDING), class_="sg-funding", alt=tr("app.shell.funding_alt")
        ),
        class_="sg-funding-strip",
    )


_ICONS = {
    "about": "<circle cx='12' cy='12' r='9'/><path d='M12 11v5'/><path d='M12 7.5v.01'/>",
    "help": (
        "<circle cx='12' cy='12' r='9'/>"
        "<path d='M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.8.4-1 .9-1 1.7'/>"
        "<path d='M12 16.5v.01'/>"
    ),
    "feedback": "<path d='M4 5h16v11H9l-4 3v-3H4z'/>",
}


def _action(id_: str, label: str) -> ui.Tag:
    svg = (
        f"<svg class='sg-act-ico' viewBox='0 0 24 24' fill='none' stroke='currentColor' "
        f"stroke-width='1.7' stroke-linecap='round' stroke-linejoin='round' "
        f"aria-hidden='true'>{_ICONS[id_]}</svg>"
    )
    return ui.nav_control(
        ui.input_action_link(
            id_, ui.TagList(ui.HTML(svg), ui.tags.span(label)), class_="sg-action"
        )
    )


def about_modal(tr: Translator) -> ui.Tag:
    # Read the version from the package - a hand-copied one drifts silently, and this
    # dialog is exactly where a reader checks what they are looking at.
    from seagarden_dst import __version__

    return ui.modal(
        ui.markdown(
            tr(
                "app.shell.about.body",
                version=__version__, repo_name=REPO_URL.split("//")[1], repo_url=REPO_URL,
            )
        ),
        title=tr("app.shell.about.title"),
        easy_close=True,
        size="l",
        footer=ui.modal_button(tr("app.shell.close")),
    )


def help_modal(tr: Translator) -> ui.Tag:
    return ui.modal(
        ui.markdown(tr("app.shell.help.body")),
        title=tr("app.shell.help.title"),
        easy_close=True,
        size="xl",
        footer=ui.modal_button(tr("app.shell.close")),
    )


def feedback_modal(tr: Translator) -> ui.Tag:
    return ui.modal(
        ui.markdown(tr("app.shell.feedback.body", repo_url=REPO_URL, email=CONTACT_EMAIL)),
        title=tr("app.shell.feedback.title"),
        easy_close=True,
        size="m",
        footer=ui.modal_button(tr("app.shell.close")),
    )


def language_menu(tr: Translator, enabled: Sequence[str]) -> ui.Tag:
    """The navbar menu of enabled languages, as RELATIVE `?lang=` links (I§5.3).

    Relative so the sub-path proxy on laguna (`/seagarden-dst/`) needs nothing. The
    current language is a marked, unlinked item. Names are endonyms, not translated.

    Built as a plain Bootstrap dropdown `Tag`, not `ui.nav_menu`: shiny's `NavMenu`
    only tagifies inside a navset container (its `tagify()` raises otherwise), which
    would make this function untestable on its own. `app_shell` wraps the returned
    tag in `ui.nav_control(...)`, which supplies its own `<li>` - so this returns a
    `<div class="dropdown">`, not another `<li>`, or the two would nest illegally
    (`<li><li>...</li></li>`). Same shape `_action`'s plain `<li>` already uses: the
    navbar item's own classes live on this inner element, not on nav_control's `<li>`.
    """
    items = []
    for code in enabled:
        name = LANGUAGE_NAMES.get(code, code)
        if code == tr.language:
            items.append(
                ui.tags.li(ui.tags.span(f"✓ {name}", class_="dropdown-item sg-lang-current"))
            )
        else:
            items.append(
                ui.tags.li(
                    ui.tags.a(name, href=f"?lang={code}", class_="dropdown-item sg-lang")
                )
            )
    return ui.tags.div(
        ui.tags.a(
            tr("app.shell.language"),
            class_="nav-link dropdown-toggle",
            data_bs_toggle="dropdown",
            href="#",
            role="button",
        ),
        ui.tags.ul(*items, class_="dropdown-menu dropdown-menu-end"),
        class_="dropdown sg-lang-menu",
    )


def draft_banner(tr: Translator) -> ui.Tag | None:
    """Bilingual notice under the navbar for a machine-draft language (I§6); None otherwise."""
    if not tr.is_draft:
        return None
    return ui.div(
        ui.tags.strong(tr("app.shell.draft_banner")),
        " ",
        english()("app.shell.draft_banner"),
        class_="sg-draft-banner",
        role="note",
    )


def _map_head() -> tuple:
    """deck.gl + MapLibre assets, when `shiny_deckgl` is installed.

    `MapWidget.ui()` returns a bare div with no dependency attached, so without this the
    map is an empty box and the failure is silent - the page renders, the panel looks
    fine, nothing draws. Imported lazily for the same reason as in `modules/site.py`:
    the package ships on a conda channel, is deliberately not a pip dependency, and
    `app/tests` imports this module, so a module-scope import turns CI red at collection.
    """
    try:
        from shiny_deckgl.ui import head_includes
    except ImportError:
        return ()
    return (head_includes(),)


def app_shell(tr: Translator, *panels, enabled: Sequence[str] = ("en",)) -> ui.Tag:
    banner = draft_banner(tr)
    header = [ui.include_css(_BRAND_CSS, method="inline")]
    if banner is not None:
        header.append(banner)
    return ui.page_navbar(
        *_map_head(),
        *panels,
        ui.nav_spacer(),
        _action("about", tr("app.shell.about")),
        _action("help", tr("app.shell.help")),
        _action("feedback", tr("app.shell.feedback")),
        ui.nav_control(language_menu(tr, enabled)),
        title=_brand(),
        id="main_nav",
        # Inlined so it loads with no extra request and works offline.
        header=ui.TagList(*header),
        window_title=tr("app.shell.window_title"),
        lang=tr.language,
        sidebar=ui.sidebar(
            ui.tags.h1(tr("app.shell.title"), class_="visually-hidden"),
            ui.h2(tr("app.shell.setup")),
            ui.help_text(tr("app.shell.workflow")),
            ui.output_ui("user_mode_slot"),
            ui.input_action_button("assess", tr("app.shell.assess"), class_="btn-primary"),
            ui.output_ui("status_slot"),
            ui.output_ui("data_source_slot"),
            _funding_strip(tr),
            width=320,
        ),
    )
