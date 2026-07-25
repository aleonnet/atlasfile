/** v0.46.0: combo rápido de modelos — agrupamento por provedor. */
import { describe, expect, it } from "vitest";
import { groupQuickModelValues } from "./modelGroups";
import type { ModelOption } from "../types";

const CATALOG: ModelOption[] = [
  { provider: "openai", model: "gpt-5.1", label: "OpenAI gpt-5.1" },
  { provider: "openai", model: "gpt-4o-mini", label: "OpenAI gpt-4o-mini" },
  { provider: "anthropic", model: "claude-fable-5", label: "Anthropic claude-fable-5" },
] as ModelOption[];

describe("groupQuickModelValues", () => {
  it("agrupa na ordem do registro de providers, com dedup e ordem de chegada dentro do grupo", () => {
    const groups = groupQuickModelValues(
      ["anthropic/claude-fable-5", "openai/gpt-4o-mini", "openai/gpt-5.1", "openai/gpt-4o-mini"],
      CATALOG
    );
    expect(groups.map((g) => g.provider)).toEqual(["openai", "anthropic"]);
    expect(groups[0].options.map((o) => o.value)).toEqual(["openai/gpt-4o-mini", "openai/gpt-5.1"]);
  });

  it("tira a marca redundante do label dentro do grupo (o optgroup já diz o provedor)", () => {
    const [openai] = groupQuickModelValues(["openai/gpt-5.1"], CATALOG);
    expect(openai.options[0].label).toBe("gpt-5.1");
  });

  it("custom fora do catálogo usa o id do modelo como label; provider desconhecido vai ao final", () => {
    const groups = groupQuickModelValues(["zprovider/z-1", "ollama/gemma4:12b", "openai/gpt-5.1"], CATALOG);
    expect(groups.map((g) => g.provider)).toEqual(["openai", "ollama", "zprovider"]);
    expect(groups[1].options[0].label).toBe("gemma4:12b");
  });

  it("ignora vazios, nulos e valores sem provider/", () => {
    const groups = groupQuickModelValues(["", null, undefined, "semdelimitador", "openai/gpt-5.1"], CATALOG);
    expect(groups).toHaveLength(1);
    expect(groups[0].options).toHaveLength(1);
  });
});
