import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import i18n from "../i18n";
import { STORAGE_KEYS } from "../lib/storage";
import { LanguageQuickSwitch } from "./LanguageQuickSwitch";

describe("LanguageQuickSwitch", () => {
  afterEach(async () => {
    await i18n.changeLanguage("pt-BR");
    localStorage.removeItem(STORAGE_KEYS.language);
  });

  it("exibe endônimos e o idioma ativo (PT-BR nos testes)", () => {
    render(<LanguageQuickSwitch />);
    const select = screen.getByLabelText("Idioma da interface") as HTMLSelectElement;
    expect(select.value).toBe("pt-BR");
    expect(screen.getByText("Português (Brasil)")).toBeInTheDocument();
    expect(screen.getByText("English (US)")).toBeInTheDocument();
  });

  it("troca ao vivo (sem reload): idioma muda, persiste e o próprio label re-renderiza", async () => {
    render(<LanguageQuickSwitch />);
    fireEvent.change(screen.getByLabelText("Idioma da interface"), { target: { value: "en-US" } });
    await waitFor(() => expect(i18n.resolvedLanguage).toBe("en-US"));
    expect(localStorage.getItem(STORAGE_KEYS.language)).toBe("en-US");
    // o aria-label do próprio select troca ao vivo — prova da re-renderização
    expect(screen.getByLabelText("Interface language")).toBeInTheDocument();
  });
});
