import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("garden_my_day_tour", {
    steps: () => [
        {
            content: "« Ma journée » affiche l'opération du jour regroupée par îlot",
            trigger: ".o_kanban_view .o_kanban_group .o_kanban_record:contains(Désherbage - Tour)",
        },
        {
            content: "Démarrer l'opération lance le chronomètre",
            trigger: ".o_kanban_record:contains(Désherbage - Tour) button[name=action_start]",
            run: "click",
        },
        {
            content: "Le badge chrono apparaît sur la carte",
            trigger: ".o_kanban_record:contains(Désherbage - Tour) .badge:contains(Chrono)",
        },
        {
            content: "Terminer l'opération",
            trigger: ".o_kanban_record:contains(Désherbage - Tour) button[name=action_done]",
            run: "click",
        },
        {
            content: "L'opération faite quitte la vue du jour",
            trigger: ".o_kanban_view:not(:has(.o_kanban_record:contains(Désherbage - Tour)))",
        },
    ],
});
