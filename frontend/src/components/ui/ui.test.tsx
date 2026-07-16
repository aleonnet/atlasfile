import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Badge } from "./badge";
import { Button } from "./button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "./card";
import { Dialog, DialogContent, DialogTitle, DialogTrigger } from "./dialog";
import { EmptyState, ErrorState } from "./empty-state";
import { Input } from "./input";
import { Skeleton } from "./skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "./tabs";

describe("ui primitives (tema AtlasFile)", () => {
  it("Button aplica variantes temadas e dispara onClick", () => {
    const onClick = vi.fn();
    render(<Button onClick={onClick}>Salvar</Button>);
    const button = screen.getByRole("button", { name: "Salvar" });
    expect(button.className).toContain("bg-primary");
    expect(button).toHaveAttribute("type", "button");
    fireEvent.click(button);
    expect(onClick).toHaveBeenCalledOnce();
  });

  it("Button variant destructive não usa o tema default do shadcn", () => {
    render(<Button variant="destructive">Excluir</Button>);
    const button = screen.getByRole("button", { name: "Excluir" });
    expect(button.className).toContain("text-destructive");
    expect(button.className).not.toContain("zinc");
  });

  it("Card compõe header/título/descrição/conteúdo", () => {
    render(
      <Card>
        <CardHeader>
          <CardTitle>Documentos</CardTitle>
          <CardDescription>37 indexados</CardDescription>
        </CardHeader>
        <CardContent>conteúdo</CardContent>
      </Card>
    );
    expect(screen.getByRole("heading", { name: "Documentos" })).toBeInTheDocument();
    expect(screen.getByText("37 indexados")).toBeInTheDocument();
  });

  it("Dialog abre pelo trigger e renderiza título acessível", () => {
    render(
      <Dialog>
        <DialogTrigger asChild>
          <Button>Abrir</Button>
        </DialogTrigger>
        <DialogContent>
          <DialogTitle>Confirmação</DialogTitle>
        </DialogContent>
      </Dialog>
    );
    fireEvent.click(screen.getByRole("button", { name: "Abrir" }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText("Confirmação")).toBeInTheDocument();
  });

  it("Tabs troca de conteúdo ao clicar", () => {
    render(
      <Tabs defaultValue="a">
        <TabsList>
          <TabsTrigger value="a">Aba A</TabsTrigger>
          <TabsTrigger value="b">Aba B</TabsTrigger>
        </TabsList>
        <TabsContent value="a">conteúdo A</TabsContent>
        <TabsContent value="b">conteúdo B</TabsContent>
      </Tabs>
    );
    expect(screen.getByText("conteúdo A")).toBeInTheDocument();
    // Radix Tabs ativa no mousedown (não no click sintético)
    fireEvent.mouseDown(screen.getByRole("tab", { name: "Aba B" }));
    expect(screen.getByText("conteúdo B")).toBeInTheDocument();
  });

  it("Input, Badge e Skeleton renderizam com classes do tema", () => {
    const { container } = render(
      <div>
        <Input placeholder="API key" />
        <Badge variant="purple">semântico</Badge>
        <Skeleton data-testid="skeleton" className="h-4 w-24" />
      </div>
    );
    expect(screen.getByPlaceholderText("API key").className).toContain("bg-panel");
    expect(screen.getByText("semântico").className).toContain("accent-purple");
    expect(container.querySelector("[data-testid=skeleton]")!.className).toContain("bg-panel-strong");
  });

  it("EmptyState e ErrorState com retry", () => {
    const onRetry = vi.fn();
    render(
      <div>
        <EmptyState title="Nenhum documento" description="Faça upload para começar" />
        <ErrorState description="Falha ao carregar" onRetry={onRetry} />
      </div>
    );
    expect(screen.getByText("Nenhum documento")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Tentar de novo/ }));
    expect(onRetry).toHaveBeenCalledOnce();
  });
});
