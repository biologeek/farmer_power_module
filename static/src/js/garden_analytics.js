import { Component, onMounted, onWillStart, onWillUnmount, useRef, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { Layout } from "@web/search/layout";
import { registry } from "@web/core/registry";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

const MIN_WIDTH = 280;
const HEIGHT = 240;
const MARGIN = { left: 56, right: 12, top: 12, bottom: 28 };

/** Valeur lisible : séparateurs de milliers, 0 à 2 décimales selon l'ordre de grandeur. */
export function formatValue(value) {
    const abs = Math.abs(value || 0);
    const digits = abs >= 100 ? 0 : abs >= 10 ? 1 : 2;
    return (value || 0).toLocaleString(undefined, { maximumFractionDigits: digits });
}

/** Graduations « rondes » couvrant [min, max] (zéro toujours inclus). */
export function niceTicks(min, max, count = 4) {
    min = Math.min(min, 0);
    max = Math.max(max, 0);
    if (min === max) {
        max = 1;
    }
    const raw = (max - min) / count;
    const magnitude = Math.pow(10, Math.floor(Math.log10(raw)));
    const step = [1, 2, 2.5, 5, 10].map((m) => m * magnitude).find((s) => s >= raw);
    const low = Math.floor(min / step) * step;
    const high = Math.ceil(max / step) * step;
    const ticks = [];
    for (let tick = low; tick <= high + step / 2; tick += step) {
        ticks.push(Math.round(tick * 1e6) / 1e6);
    }
    return ticks;
}

/**
 * Graphique générique dessiné en SVG / HTML, sans librairie externe. Il reçoit un descriptif neutre
 * (`garden.analytics`) : type `bar`, `stacked`, `line`, `hbar` ou `donut`.
 */
export class GardenChart extends Component {
    static template = "garden.GardenChart";
    static props = { chart: Object };

    setup() {
        this.root = useRef("root");
        this.size = useState({ width: 560 });
        // Le SVG est dessiné à la largeur réelle de la carte pour garder des textes lisibles.
        this.observer = new ResizeObserver(() => this.measure());
        onMounted(() => {
            this.measure();
            this.observer.observe(this.root.el);
        });
        onWillUnmount(() => this.observer.disconnect());
    }

    measure() {
        const width = Math.round(this.root.el?.clientWidth || 0);
        if (width >= MIN_WIDTH && width !== this.size.width) {
            this.size.width = width;
        }
    }

    get chart() {
        return this.props.chart;
    }

    get unit() {
        return this.chart.unit ? ` ${this.chart.unit}` : "";
    }

    format(value) {
        return formatValue(value) + this.unit;
    }

    formatTick(value) {
        return formatValue(value);
    }

    short(label) {
        return label.length > 12 ? `${label.slice(0, 11)}…` : label;
    }

    get showLegend() {
        return this.chart.series.length > 1;
    }

    /** Ligne des barres horizontales : largeur proportionnelle à la valeur absolue la plus grande. */
    get hbarRows() {
        const values = this.chart.series[0].values;
        const max = Math.max(...values.map((v) => Math.abs(v)), 0);
        return this.chart.labels.map((label, i) => ({
            label,
            value: values[i],
            width: max ? Math.round((Math.abs(values[i]) / max) * 100) : 0,
        }));
    }

    get donut() {
        const values = this.chart.series[0].values.map((v) => Math.max(v, 0));
        const total = values.reduce((a, b) => a + b, 0);
        const radius = 40;
        const circumference = 2 * Math.PI * radius;
        let offset = 0;
        const segments = values.map((value, i) => {
            const share = total ? value / total : 0;
            const segment = {
                index: i,
                label: this.chart.labels[i],
                value,
                percent: Math.round(share * 100),
                dash: `${share * circumference} ${circumference - share * circumference}`,
                offset: -offset * circumference,
            };
            offset += share;
            return segment;
        });
        return { segments, radius };
    }

    /** Géométrie des graphiques en barres (groupées ou empilées) et en courbes. */
    get plot() {
        const { labels, series, type } = this.chart;
        const stacked = type === "stacked";
        let min = 0;
        let max = 0;
        for (let i = 0; i < labels.length; i++) {
            if (stacked) {
                const positive = series.reduce((sum, s) => sum + Math.max(s.values[i], 0), 0);
                const negative = series.reduce((sum, s) => sum + Math.min(s.values[i], 0), 0);
                max = Math.max(max, positive);
                min = Math.min(min, negative);
            } else {
                for (const s of series) {
                    max = Math.max(max, s.values[i]);
                    min = Math.min(min, s.values[i]);
                }
            }
        }
        const ticks = niceTicks(min, max);
        const low = ticks[0];
        const high = ticks[ticks.length - 1];
        const width = this.size.width;
        const plotWidth = width - MARGIN.left - MARGIN.right;
        const plotHeight = HEIGHT - MARGIN.top - MARGIN.bottom;
        const y = (value) => MARGIN.top + ((high - value) / (high - low)) * plotHeight;
        const band = plotWidth / labels.length;
        const x = (i) => MARGIN.left + band * (i + 0.5);
        const result = {
            width,
            right: width - MARGIN.right,
            band,
            zero: y(0),
            ticks: ticks.map((tick) => ({ value: tick, y: y(tick) })),
            xLabels: labels.map((label, i) => ({ label, short: this.short(label), x: x(i) })),
            bars: [],
            lines: [],
        };
        if (type === "line") {
            result.lines = series.map((s, index) => ({
                index: s.color ?? index,
                name: s.name,
                points: s.values.map((v, i) => ({ x: x(i), y: y(v), value: v, label: labels[i] })),
                path: s.values.map((v, i) => `${x(i)},${y(v)}`).join(" "),
            }));
            return result;
        }
        const inner = band * 0.72;
        const barWidth = stacked ? inner : inner / series.length;
        for (let i = 0; i < labels.length; i++) {
            let positive = 0;
            let negative = 0;
            series.forEach((s, index) => {
                const value = s.values[i];
                if (!value) {
                    return;
                }
                let top;
                let bottom;
                if (stacked) {
                    if (value >= 0) {
                        bottom = positive;
                        positive += value;
                        top = positive;
                    } else {
                        top = negative;
                        negative += value;
                        bottom = negative;
                    }
                } else {
                    top = Math.max(value, 0);
                    bottom = Math.min(value, 0);
                }
                result.bars.push({
                    index: s.color ?? index,
                    x: x(i) - inner / 2 + (stacked ? 0 : index * barWidth),
                    y: y(top),
                    width: Math.max(barWidth - (stacked ? 0 : 1), 1),
                    height: Math.max(y(bottom) - y(top), 1),
                    title: `${labels[i]} - ${s.name}: ${this.format(value)}`,
                });
            });
        }
        return result;
    }
}

/**
 * Tableau de bord thématique : l'action cliente reçoit le thème dans son contexte
 * (`occupation`, `crops`, `work`, `finance`, `years`) et dessine les chiffres clés et les graphiques
 * renvoyés par `garden.analytics.get_data`.
 */
class GardenAnalyticsAction extends Component {
    static template = "garden.GardenAnalytics";
    static components = { Layout, GardenChart };
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.theme = this.props.action.context?.theme || "occupation";
        this.state = useState({ data: null, loading: false });
        onWillStart(() => this.load(null, true));
    }

    async load(year = null, refresh = false) {
        this.state.loading = true;
        try {
            this.state.data = await this.orm.call("garden.analytics", "get_data", [this.theme], { year, refresh });
        } finally {
            this.state.loading = false;
        }
    }

    onYearChange(ev) {
        return this.load(parseInt(ev.target.value, 10));
    }

    onRefresh() {
        return this.load(this.state.data?.year, true);
    }

    get canRefresh() {
        return this.theme === "finance" || this.theme === "years";
    }

    formatKpi(kpi) {
        return typeof kpi.value === "string" ? kpi.value : formatValue(kpi.value);
    }
}

registry.category("actions").add("garden_analytics", GardenAnalyticsAction);
