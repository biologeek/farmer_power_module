import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("garden_gantt_tour", {
    steps: () => [
        {
            content: "The crop plan shows the expected bars",
            trigger: ".o_garden_gantt .o_garden_gantt_bar_planned",
        },
        {
            content: "The actual bars are shown",
            trigger: ".o_garden_gantt .o_garden_gantt_bar_real",
        },
        {
            content: "The legend lists the botanical families",
            trigger: ".o_garden_gantt .o_garden_gantt_legend .o_garden_family_solanaceae",
        },
        {
            content: "Filtrer sur la saison",
            trigger: ".o_garden_gantt select:first",
            run: "select Saison Gantt 2027",
        },
        {
            content: "Un clic sur une barre ouvre la culture",
            trigger: ".o_garden_gantt .o_garden_gantt_bar_planned:contains(Tomate Gantt)",
            run: "click",
        },
        {
            content: "La fiche de la culture s'affiche",
            trigger: ".o_form_view .o_field_widget[name=name]:contains(T-2027-GN01-01)",
        },
    ],
});
