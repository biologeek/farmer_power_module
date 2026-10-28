import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("garden_compliance_tour", {
    steps: () => [
        {
            content: "L'écran du registre phytosanitaire s'ouvre avec ses boutons",
            trigger: ".o_form_view .o_statusbar_buttons button[name=action_compute]",
        },
        {
            content: "Calculer le registre",
            trigger: ".o_form_view button[name=action_compute]",
            run: "click",
        },
        {
            content: "La ligne du traitement apparaît avec son numéro d'AMM",
            trigger: ".o_form_view .o_list_renderer tr.o_data_row:contains(AMM-TOUR-0001)",
        },
        {
            content: "Les boutons d'impression et d'export sont disponibles",
            trigger: ".o_form_view button[name=action_print]:visible, .o_form_view button[name=action_export_xlsx]",
        },
    ],
});
