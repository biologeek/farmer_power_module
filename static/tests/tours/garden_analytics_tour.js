import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("garden_analytics_tour", {
    steps: () => [
        {
            content: "The dashboard shows its key figures",
            trigger: ".o_garden_analytics .o_garden_kpi",
        },
        {
            content: "At least one chart is drawn",
            trigger: ".o_garden_analytics .o_garden_card .o_garden_chart",
        },
        {
            content: "The charts hold bars, curves or segments",
            trigger: ".o_garden_chart svg rect, .o_garden_chart svg polyline, .o_garden_chart svg circle, .o_garden_chart .o_garden_bar_row",
        },
        {
            content: "The year selector is available when the theme has a year filter",
            trigger: ".o_garden_analytics .o_garden_year, .o_garden_analytics[data-theme=years]",
        },
    ],
});
