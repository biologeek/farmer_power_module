import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("garden_gantt_tour", {
    steps: () => [
        {
            content: "Le plan de culture affiche les barres prévues",
            trigger: ".o_garden_gantt .o_garden_gantt_bar_planned",
        },
        {
            content: "Les barres réalisées sont affichées",
            trigger: ".o_garden_gantt .o_garden_gantt_bar_real",
        },
        {
            content: "La légende liste les familles botaniques",
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
