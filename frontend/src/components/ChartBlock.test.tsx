/// <reference types="@testing-library/jest-dom/vitest" />
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ChartBlock } from "./ChartBlock";

describe("ChartBlock", () => {
  it("renders a bar chart from valid JSON", () => {
    const json = JSON.stringify({
      type: "bar",
      title: "Documentos por domínio",
      data: [
        { name: "Jurídico", value: 145 },
        { name: "Financeiro", value: 89 },
      ],
    });
    const { container } = render(<ChartBlock jsonString={json} />);
    expect(screen.getByText("Documentos por domínio")).toBeInTheDocument();
    expect(container.querySelector(".chart-block-container")).toBeInTheDocument();
    expect(container.querySelector(".recharts-responsive-container")).toBeInTheDocument();
  });

  it("renders a pie chart from valid JSON", () => {
    const json = JSON.stringify({
      type: "pie",
      title: "Distribuição por extensão",
      data: [
        { name: "PDF", value: 200 },
        { name: "DOCX", value: 50 },
      ],
    });
    const { container } = render(<ChartBlock jsonString={json} />);
    expect(screen.getByText("Distribuição por extensão")).toBeInTheDocument();
    expect(container.querySelector(".chart-block-container")).toBeInTheDocument();
  });

  it("renders a stacked bar chart with multiple series", () => {
    const json = JSON.stringify({
      type: "stacked_bar",
      title: "Tokens por dia",
      data: [
        { name: "01/jan", input: 100, output: 50 },
        { name: "02/jan", input: 120, output: 80 },
      ],
      series: ["input", "output"],
    });
    const { container } = render(<ChartBlock jsonString={json} />);
    expect(screen.getByText("Tokens por dia")).toBeInTheDocument();
    expect(container.querySelector(".chart-block-container")).toBeInTheDocument();
  });

  it("renders a horizontal bar chart", () => {
    const json = JSON.stringify({
      type: "horizontal_bar",
      title: "Ranking por tamanho",
      data: [
        { name: "doc_a.pdf", value: 5000 },
        { name: "doc_b.pdf", value: 3000 },
      ],
    });
    const { container } = render(<ChartBlock jsonString={json} />);
    expect(screen.getByText("Ranking por tamanho")).toBeInTheDocument();
    expect(container.querySelector(".chart-block-container")).toBeInTheDocument();
  });

  it("falls back to <pre> for invalid JSON", () => {
    const badJson = "not valid json {{{";
    const { container } = render(<ChartBlock jsonString={badJson} />);
    expect(container.querySelector(".chart-block-fallback")).toBeInTheDocument();
    expect(container.querySelector(".chart-block-container")).not.toBeInTheDocument();
  });

  it("falls back to <pre> for unknown chart type", () => {
    const json = JSON.stringify({
      type: "waterfall",
      title: "Unknown",
      data: [{ name: "A", value: 1 }],
    });
    const { container } = render(<ChartBlock jsonString={json} />);
    expect(container.querySelector(".chart-block-fallback")).toBeInTheDocument();
  });

  it("falls back to <pre> for empty data array", () => {
    const json = JSON.stringify({ type: "bar", title: "Empty", data: [] });
    const { container } = render(<ChartBlock jsonString={json} />);
    expect(container.querySelector(".chart-block-fallback")).toBeInTheDocument();
  });

  it("falls back to <pre> for missing data field", () => {
    const json = JSON.stringify({ type: "bar", title: "No data" });
    const { container } = render(<ChartBlock jsonString={json} />);
    expect(container.querySelector(".chart-block-fallback")).toBeInTheDocument();
  });

  it("renders line chart", () => {
    const json = JSON.stringify({
      type: "line",
      title: "Tendência",
      data: [
        { name: "Jan", value: 10 },
        { name: "Feb", value: 20 },
      ],
    });
    const { container } = render(<ChartBlock jsonString={json} />);
    expect(screen.getByText("Tendência")).toBeInTheDocument();
    expect(container.querySelector(".chart-block-container")).toBeInTheDocument();
  });

  it("renders area chart", () => {
    const json = JSON.stringify({
      type: "area",
      title: "Volume",
      data: [
        { name: "Jan", value: 100 },
        { name: "Feb", value: 200 },
      ],
    });
    const { container } = render(<ChartBlock jsonString={json} />);
    expect(screen.getByText("Volume")).toBeInTheDocument();
    expect(container.querySelector(".chart-block-container")).toBeInTheDocument();
  });

  it("renders composed chart", () => {
    const json = JSON.stringify({
      type: "composed",
      title: "Custo e tendência",
      data: [
        { name: "Jan", custo: 100, media: 90 },
        { name: "Feb", custo: 150, media: 120 },
      ],
      series: ["custo", "media"],
    });
    const { container } = render(<ChartBlock jsonString={json} />);
    expect(screen.getByText("Custo e tendência")).toBeInTheDocument();
    expect(container.querySelector(".chart-block-container")).toBeInTheDocument();
  });

  it("renders treemap", () => {
    const json = JSON.stringify({
      type: "treemap",
      title: "Hierarquia",
      data: [
        { name: "Jurídico", value: 100 },
        { name: "Financeiro", value: 80 },
        { name: "RH", value: 30 },
      ],
    });
    const { container } = render(<ChartBlock jsonString={json} />);
    expect(screen.getByText("Hierarquia")).toBeInTheDocument();
    expect(container.querySelector(".chart-block-container")).toBeInTheDocument();
  });

  it("renders chart without title", () => {
    const json = JSON.stringify({
      type: "bar",
      data: [{ name: "A", value: 10 }],
    });
    const { container } = render(<ChartBlock jsonString={json} />);
    expect(container.querySelector(".chart-block-container")).toBeInTheDocument();
    expect(container.querySelector(".chart-block-title")).not.toBeInTheDocument();
  });

  it("renders heatmap matrix with values and zero placeholders", () => {
    const json = JSON.stringify({
      type: "heatmap",
      title: "Domínio × tipo",
      series: ["contrato", "parecer"],
      data: [
        { name: "Jurídico", contrato: 3, parecer: 2 },
        { name: "Financeiro", contrato: 0 },
      ],
    });
    render(<ChartBlock jsonString={json} />);
    expect(screen.getByText("Domínio × tipo")).toBeInTheDocument();
    expect(screen.getByText("Jurídico")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    // células zero/ausentes viram placeholder "·"
    expect(screen.getAllByText("·").length).toBeGreaterThan(0);
  });

  it("renders facets as small multiples (3 variáveis)", () => {
    const json = JSON.stringify({
      type: "heatmap",
      title: "Domínio × tipo por formato",
      series: ["contrato"],
      facets: [
        { title: "PDF", data: [{ name: "Jurídico", contrato: 3 }] },
        { title: "DOCX", data: [{ name: "Jurídico", contrato: 1 }] },
      ],
    });
    render(<ChartBlock jsonString={json} />);
    expect(screen.getByText("PDF")).toBeInTheDocument();
    expect(screen.getByText("DOCX")).toBeInTheDocument();
    expect(screen.getAllByText("Jurídico")).toHaveLength(2);
  });
});
