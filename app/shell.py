"""DST app shell: branding, sidebar, top-bar actions, English t() seam.

Same shape as the NiD4OCEAN DST shell. The brand theme is `www/seagarden.css`, inlined
into the page so it needs no static route and survives the sub-path proxy and an
offline host. The two logo PNGs are base64-inlined for the same reason: a broken image
link degrades silently to an empty box, and the funding lockup is one Interreg's
communication rules require to be visible.
"""

from __future__ import annotations

import base64
from pathlib import Path

from shiny import ui

_WWW = Path(__file__).parent / "www"
_BRAND_CSS = _WWW / "seagarden.css"
_ICON = _WWW / "seagarden-icon.png"  # the circular mark, from the Communication folder
_FUNDING = _WWW / "seagarden-funding-lockup.png"  # SeaGarden | Interreg South Baltic | EU

REPO_URL = "https://github.com/razinkele/seagarden-dst"
CONTACT_EMAIL = "arturas.razinkovas-baziukas@ku.lt"


def t(key: str) -> str:  # i18n seam - English passthrough for the prototype
    return key


def _data_uri(path: Path) -> str:
    """Base64-inline a PNG so the page needs no static-asset route for it."""
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def _brand() -> ui.Tag:
    """Navbar brand: the circular icon mark, the name with the lime 'Sea', a DST tag."""
    return ui.tags.span(
        ui.tags.img(src=_data_uri(_ICON), class_="sg-logo", alt=""),
        ui.tags.span(ui.tags.b("Sea"), "Garden", class_="sg-name"),
        ui.tags.span("DST", class_="sg-dst"),
        class_="sg-brand",
    )


def _funding_strip() -> ui.Tag:
    """The full lockup on a white strip: it is dark-on-white and cannot sit in the bar."""
    return ui.div(
        ui.tags.img(
            src=_data_uri(_FUNDING),
            class_="sg-funding",
            alt="SeaGarden - Interreg South Baltic, co-funded by the European Union",
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


def about_modal() -> ui.Tag:
    # Read the version from the package - a hand-copied one drifts silently, and this
    # dialog is exactly where a reader checks what they are looking at.
    from seagarden_dst import __version__

    return ui.modal(
        ui.markdown(
            "The **SeaGarden Decision Support Tool** helps plan community-driven "
            "regenerative marine farms in the South Baltic. Pick a site, choose what to "
            "grow and at what scale, and the tool returns a siting verdict, an expected "
            "harvest, and the nitrogen, phosphorus and carbon that harvest removes from "
            "the water.\n\n"
            "**What it gives you**\n\n"
            "- A siting verdict computed as the **minimum** across constraint classes, "
            "with the binding constraint named. Not a weighted index: a site with a "
            "fatal legal exclusion must not score 'moderate' because the water is good.\n"
            "- A **calibration tier** beside every number - locally calibrated, "
            "regionally extrapolated, literature prior, or contraindicated. Before the "
            "WP3 pilot data arrives, essentially every South Baltic figure is a "
            "literature prior, and the tool says so on the number itself.\n"
            "- **Eutrophication pressure** from the MARBEFES bow-tie, and optional "
            "**nutrient forcing** from the EUTROPY box model, both reported beside the "
            "ranking and never folded into it.\n\n"
            "- **Programme** - Interreg South Baltic 2021-2027 · **SeaGarden** "
            "(STHB.02.02-IP.01-0006/25)\n"
            "- **Work package / activity** - WP2 / A2.3 · Deliverable **D2.2**\n"
            "- **Lead** - Klaipeda University, Marine Research Institute\n"
            f"- **Status** - prototype · core `v{__version__}`\n\n"
            f"Source & issues: [{REPO_URL.split('//')[1]}]({REPO_URL})\n\n"
            "*Prototype. Outputs are indicative and are not a basis for permitting or "
            "consent. Co-funded by the European Union; views expressed are the authors' "
            "only.*"
        ),
        title="About the SeaGarden DST",
        easy_close=True,
        size="l",
        footer=ui.modal_button("Close"),
    )


def help_modal() -> ui.Tag:
    return ui.modal(
        ui.markdown(
            "**Workflow**\n\n"
            "1. **Site** - choose a sub-region. In the delivered tool you will draw a "
            "polygon; the prototype uses placeholder conditions per sub-region.\n"
            "2. **Catalogue** - choose species, cultivation method and scale.\n"
            "3. **Assess** - the sidebar button. Results and Report stay blank until "
            "you press it, and are cleared again the moment you change the site.\n"
            "4. **Results** - ranked options, the binding constraint for each, and the "
            "nutrient removal with its calibration tier.\n"
            "5. **Report** - the assessment as text, caveats included.\n\n"
            "**Reading the calibration tiers**\n\n"
            "| Tier | Meaning | How it is shown |\n"
            "|---|---|---|\n"
            "| A | Fitted to SeaGarden pilot data | value with an interval |\n"
            "| B | Fitted elsewhere in the Baltic | value as a range |\n"
            "| C | Literature prior, no local validation | order-of-magnitude band |\n"
            "| D | Contraindicated - a local finding contradicts the model | the "
            "finding, in place of the number |\n\n"
            "The tier D case worth knowing: sugar kelp below about 16 psu. The salinity "
            "scaling returns a small positive yield; the OLAMUR pilot found outright "
            "cultivation failure at 5.5-6.5 psu. The tool shows the finding."
        ),
        title="Using the SeaGarden DST",
        easy_close=True,
        size="xl",
        footer=ui.modal_button("Close"),
    )


def feedback_modal() -> ui.Tag:
    return ui.modal(
        ui.markdown(
            "This is a co-development prototype for WP2 A2.3. Concrete feedback - which "
            "panel, which site, what you expected - is the most useful kind.\n\n"
            f"- **Open an issue** - [{REPO_URL}/issues/new]({REPO_URL}/issues/new)\n"
            f"- **Email** - [{CONTACT_EMAIL}](mailto:{CONTACT_EMAIL}"
            "?subject=SeaGarden%20DST%20feedback)"
        ),
        title="Send feedback",
        easy_close=True,
        size="m",
        footer=ui.modal_button("Close"),
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


def app_shell(*panels) -> ui.Tag:
    return ui.page_navbar(
        *_map_head(),
        *panels,
        ui.nav_spacer(),
        _action("about", t("About")),
        _action("help", t("Help")),
        _action("feedback", t("Feedback")),
        title=_brand(),
        id="main_nav",
        # Inlined so it loads with no extra request and works offline.
        header=ui.include_css(_BRAND_CSS, method="inline"),
        window_title="SeaGarden DST",
        sidebar=ui.sidebar(
            ui.tags.h1(t("SeaGarden Decision Support Tool"), class_="visually-hidden"),
            ui.h2(t("Setup")),
            ui.help_text(
                t(
                    "Workflow: 1) pick a Site · 2) choose species, method and scale in "
                    "Catalogue · 3) click Assess · 4) read Results and Report."
                )
            ),
            ui.output_ui("user_mode_slot"),
            ui.input_action_button("assess", t("Assess"), class_="btn-primary"),
            ui.output_ui("status_slot"),
            ui.output_ui("data_source_slot"),
            _funding_strip(),
            width=320,
        ),
    )
