import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { STORAGE_KEYS } from "../lib/storage";
import { LanguageQuickSwitch } from "./LanguageQuickSwitch";

const reloadSpy = vi.fn();
const originalLocation = window.location;

describe("LanguageQuickSwitch", () => {
  afterEach(() => {
    Object.defineProperty(window, "location", { value: originalLocation, writable: true });
    localStorage.removeItem(STORAGE_KEYS.language);
    reloadSpy.mockClear();
  });

  it("exibe endônimos e o idioma ativo (PT-BR nos testes)", () => {
    render(<LanguageQuickSwitch />);
    const select = screen.getByLabelText("Idioma da interface") as HTMLSelectElement;
    expect(select.value).toBe("pt-BR");
    expect(screen.getByText("Português (Brasil)")).toBeInTheDocument();
    expect(screen.getByText("English (US)")).toBeInTheDocument();
  });

  it("persiste a escolha e recarrega a página", () => {
    Object.defineProperty(window, "location", {
      value: { ...originalLocation, reload: reloadSpy },
      writable: true,
    });
    render(<LanguageQuickSwitch />);
    fireEvent.change(screen.getByLabelText("Idioma da interface"), { target: { value: "en-US" } });
    expect(localStorage.getItem(STORAGE_KEYS.language)).toBe("en-US");
    expect(reloadSpy).toHaveBeenCalledOnce();
  });
});
