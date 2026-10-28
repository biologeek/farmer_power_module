import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("garden_dashboard_tour", {
    steps: () => [
        {
            content: "Le tableau de bord affiche les chiffres clés",
            trigger: ".o_garden_dashboard .o_garden_kpi",
        },
        {
            content: "Les cartes de marge par espèce et de temps par catégorie sont là",
            trigger: ".o_garden_dashboard .o_garden_card:contains(Marge par espèce) .o_garden_bar_row",
        },
        {
            content: "Le classement des cultures à l'heure liste la culture du test",
            trigger: ".o_garden_ranking_row:contains(Tomate tour)",
            run: "click",
        },
        {
            content: "Un clic ouvre la fiche de la culture avec son onglet Rentabilité",
            trigger: ".o_form_view .nav-link:contains(Rentabilité)",
        },
    ],
});
