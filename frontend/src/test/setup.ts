import "@testing-library/jest-dom/vitest";

// jsdom não implementa ResizeObserver/scrollIntoView (usados por cmdk/Radix)
if (typeof globalThis.ResizeObserver === "undefined") {
  globalThis.ResizeObserver = class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof globalThis.ResizeObserver;
}

if (typeof Element !== "undefined" && !Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}

// jsdom não implementa matchMedia (usado por AuroraField/framer-motion)
if (typeof window !== "undefined" && typeof window.matchMedia !== "function") {
  window.matchMedia = (query: string) =>
    ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    }) as MediaQueryList;
}

// O App de produção usa o queryClient singleton — limpar o cache entre testes
// garante que mocks por teste não sejam mascarados por dados de teste anterior.
import { afterEach } from "vitest";
import { queryClient } from "../lib/queryClient";

afterEach(() => {
  queryClient.clear();
});
