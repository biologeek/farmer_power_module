import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("garden_dashboard_tour", {
    steps: () => [
        {
            content: "The dashboard shows the key figures",
            trigger: ".o_garden_dashboard .o_garden_kpi",
        },
        {
            content: "The margin per species and time per category cards are there",
            trigger: ".o_garden_dashboard .o_garden_card:contains(Margin per Species) .o_garden_bar_row",
        },
        {
            content: "The per-hour crop ranking lists the test crop",
            trigger: ".o_garden_ranking_row:contains(Tomate tour)",
            run: "click",
        },
        {
            content: "A click opens the crop form with its Profitability tab",
            trigger: ".o_form_view .nav-link:contains(Profitability)",
        },
    ],
});
