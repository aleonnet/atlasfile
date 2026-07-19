import { afterEach, describe, expect, it } from "vitest";
import i18n from "../i18n";
import { suggestedTemplateSlug } from "./templates";

afterEach(async () => {
  await i18n.changeLanguage("pt-BR");
});

describe("suggestedTemplateSlug", () => {
  it("PT-BR sugere o default", () => {
    expect(suggestedTemplateSlug()).toBe("default");
  });
  it("EN-US sugere o default-en", async () => {
    await i18n.changeLanguage("en-US");
    expect(suggestedTemplateSlug()).toBe("default-en");
  });
});
