import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("garden_my_day_tour", {
    steps: () => [
        {
            content: "\"My Day\" shows the overdue operation grouped by block",
            trigger: ".o_kanban_view .o_kanban_group .o_kanban_record:contains(Weeding - Tour)",
        },
        {
            content: "Starting the operation starts the timer",
            trigger: ".o_kanban_record:contains(Weeding - Tour) button[name=action_start]",
            run: "click",
        },
        {
            content: "The timer badge appears on the card",
            trigger: ".o_kanban_record:contains(Weeding - Tour) .badge:contains(Timer)",
        },
        {
            content: "Complete the operation",
            trigger: ".o_kanban_record:contains(Weeding - Tour) button[name=action_done]",
            run: "click",
        },
        {
            content: "The done operation leaves the day view",
            trigger: ".o_kanban_view:not(:has(.o_kanban_record:contains(Weeding - Tour)))",
        },
    ],
});
