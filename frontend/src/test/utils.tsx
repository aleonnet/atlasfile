import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, type RenderOptions, type RenderResult } from "@testing-library/react";

/** QueryClient determinístico para testes: sem retry (erros aparecem na 1ª),
 *  staleTime 0 (invalidations sempre refetcham) e gcTime Infinity (gcTime 0 no
 *  v5 causa cancelamentos espúrios de queries em desmontagem). */
export function createTestQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: 0, gcTime: Infinity, refetchOnWindowFocus: false },
      mutations: { retry: false },
    },
  });
}

type ProviderRender = RenderResult & { queryClient: QueryClient };

/** Render padrão dos testes de componentes que usam useQuery/useMutation.
 *  Expõe o queryClient para invalidations manuais em asserts pós-render. */
export function renderWithProviders(ui: React.ReactElement, options?: RenderOptions): ProviderRender {
  const queryClient = createTestQueryClient();
  const result = render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>, options);
  return { ...result, queryClient };
}
