import { QueryClient } from "@tanstack/react-query";

/** QueryClient singleton do app — importável fora de componentes (adaptador do
 *  bus, pontes SSE→cache). Defaults pensados para o keep-alive de telas: com
 *  todas as views montadas, focus-refetch causaria rajadas; atualização vem de
 *  invalidations pós-mutação, SSE e dos refetchIntervals que já existiam. */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      gcTime: 5 * 60_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});
