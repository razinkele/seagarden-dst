"""Site panel - choose where.

In the delivered tool this is a map with polygon drawing over the curated layers of
specification section 6. In the prototype it is a sub-region picker over
`forcing.PLACEHOLDER_SITES`, behind the same `SiteContext` contract, so replacing it
touches this module and nothing else.
"""

from __future__ import annotations

from shiny import module, reactive, render, ui

from seagarden_dst import REGIONS, SiteContext


@module.ui
def site_ui() -> ui.Tag:
    return ui.layout_sidebar(
        ui.sidebar(
            ui.input_select("region", "Sub-region", choices=REGIONS, selected="LT-coastal"),
            ui.input_text("label", "Site name (optional)", placeholder="e.g. Melnrage pilot"),
            ui.input_action_button("set_site", "Use this site", class_="btn-outline-primary"),
            width=340,
        ),
        ui.card(ui.card_header("Site conditions"), ui.output_ui("conditions")),
        ui.card(
            ui.card_header("Where these numbers come from"),
            ui.markdown(
                "These are **placeholder conditions**, one set per sub-region: plausible "
                "order-of-magnitude values, not measurements. Every result derived from "
                "them is a literature prior.\n\n"
                "In the delivered tool this panel becomes a map. You draw a polygon and "
                "the conditions are read from the curated layers - Copernicus Marine "
                "reanalysis for salinity, temperature and nutrients, EMODnet for "
                "bathymetry and human use, HELCOM for protected areas. The contract "
                "between this panel and the model core does not change."
            ),
        ),
    )


@module.server
def site_server(input, output, session, state) -> None:  # noqa: A002
    @reactive.effect
    # ignore_init: an action-button event fires once at startup, which would commit
    # a site the user never chose and put the app straight into 'Site ready'.
    @reactive.event(input.set_site, ignore_init=True)
    def _set_site():
        region = input.region()
        label = (input.label() or "").strip() or REGIONS[region]
        state.context.set(SiteContext.from_region(region, label=label))
        state.site_label.set(label)

    @output
    @render.ui
    def conditions():
        region = input.region()
        context = SiteContext.from_region(region)
        c = context.conditions
        rows = [
            ("Salinity", f"{c.salinity_psu:g} psu"),
            ("Mean temperature", f"{c.mean_temp_c:g} °C"),
            ("Summer / winter temperature", f"{c.summer_temp_c:g} / {c.winter_temp_c:g} °C"),
            ("Dissolved inorganic nitrogen", f"{c.din_umol_l:g} µmol/L"),
            ("Dissolved inorganic phosphorus", f"{c.dip_umol_l:g} µmol/L"),
            ("Depth", f"{c.depth_m:g} m"),
            ("Significant wave height", f"{c.significant_wave_m:g} m"),
            ("PAR at cultivation depth", f"{c.par_at_depth():.0f} µmol photons/m²/s"),
        ]
        return ui.TagList(
            ui.tags.table(
                ui.tags.tbody(
                    *[
                        ui.tags.tr(
                            ui.tags.td(k, style="padding:.15rem .9rem .15rem 0;opacity:.75;"),
                            ui.tags.td(
                                v,
                                style="padding:.15rem 0;font-variant-numeric:tabular-nums;",
                            ),
                        )
                        for k, v in rows
                    ]
                ),
                style="width:100%;",
            ),
            ui.p(
                ui.tags.small(
                    f"Data confidence: low (placeholder). Calibration domain: {region}."
                )
            ),
        )
