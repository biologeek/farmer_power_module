import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("garden_compliance_tour", {
    steps: () => [
        {
            content: "The plant protection register screen opens with its buttons",
            trigger: ".o_form_view .o_statusbar_buttons button[name=action_compute]",
        },
        {
            content: "Calculer le registre",
            trigger: ".o_form_view button[name=action_compute]",
            run: "click",
        },
        {
            content: "The treatment line appears with its MA number",
            trigger: ".o_form_view .o_list_renderer tr.o_data_row:contains(AMM-TOUR-0001)",
        },
        {
            content: "Les boutons d'impression et d'export sont disponibles",
            trigger: ".o_form_view button[name=action_print]:visible, .o_form_view button[name=action_export_xlsx]",
        },
    ],
});
