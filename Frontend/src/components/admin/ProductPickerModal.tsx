import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Search, Check, Loader2, ImageIcon } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api/client";
import { queryKeys } from "@/lib/api/queryKeys";
import { formatINR } from "@/lib/format";
import type { ProductListResponse } from "@/types/admin";

interface ProductPickerModalProps {
  open: boolean;
  onClose: () => void;
  onSelect: (ids: string[]) => void;
  excludeIds?: string[];
  title?: string;
  loading?: boolean;
}

export function ProductPickerModal({
  open,
  onClose,
  onSelect,
  excludeIds = [],
  title = "Add Products",
  loading = false,
}: ProductPickerModalProps) {
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const debouncedSearch = useDebounce(search, 300);

  const params = useMemo(
    () => ({ search: debouncedSearch || undefined, page: 1, page_size: 50, status: "active" }),
    [debouncedSearch]
  );

  const { data, isLoading } = useQuery({
    queryKey: queryKeys.admin.products(params),
    queryFn: () => api.get<ProductListResponse>("/admin/products", { params }),
    enabled: open,
    staleTime: 30_000,
  });

  const available = (data?.items ?? []).filter((p) => !excludeIds.includes(p.id));

  function toggle(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function handleConfirm() {
    onSelect([...selected]);
    setSelected(new Set());
    setSearch("");
    onClose();
  }

  function handleClose() {
    setSelected(new Set());
    setSearch("");
    onClose();
  }

  return (
    <Dialog open={open} onOpenChange={(v) => !v && handleClose()}>
      <DialogContent className="max-w-2xl max-h-[80vh] flex flex-col p-0 gap-0">
        <DialogHeader className="px-6 pt-6 pb-4 border-b border-border shrink-0">
          <DialogTitle className="font-display text-xl">{title}</DialogTitle>
        </DialogHeader>

        <div className="px-6 py-3 border-b border-border shrink-0">
          <div className="flex items-center gap-2 border border-border px-3 py-2">
            <Search className="size-4 text-muted-foreground shrink-0" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search by name or SKU…"
              className="flex-1 bg-transparent outline-none text-sm"
              autoFocus
            />
          </div>
        </div>

        <div className="flex-1 overflow-y-auto">
          {isLoading ? (
            <div className="flex items-center justify-center py-16">
              <Loader2 className="size-6 animate-spin text-muted-foreground" />
            </div>
          ) : available.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-muted-foreground text-sm">
              {search ? "No products match your search." : "No products available to add."}
            </div>
          ) : (
            <div className="divide-y divide-border">
              {available.map((p) => {
                const isSelected = selected.has(p.id);
                return (
                  <button
                    key={p.id}
                    type="button"
                    onClick={() => toggle(p.id)}
                    className={`w-full flex items-center gap-3 px-6 py-3 text-left transition ${
                      isSelected ? "bg-accent/10" : "hover:bg-secondary/60"
                    }`}
                  >
                    <div
                      className={`size-5 border shrink-0 flex items-center justify-center transition ${
                        isSelected
                          ? "bg-foreground border-foreground text-background"
                          : "border-border"
                      }`}
                    >
                      {isSelected && <Check className="size-3" />}
                    </div>
                    {p.primary_image ? (
                      <img
                        src={p.primary_image}
                        alt=""
                        className="size-10 object-cover bg-secondary shrink-0"
                      />
                    ) : (
                      <div className="size-10 bg-secondary shrink-0 flex items-center justify-center">
                        <ImageIcon className="size-4 text-muted-foreground" />
                      </div>
                    )}
                    <div className="flex-1 min-w-0">
                      <p className="text-sm line-clamp-1">{p.name}</p>
                      <p className="text-xs text-muted-foreground font-mono">{p.sku}</p>
                    </div>
                    <div className="text-sm font-display shrink-0">
                      {formatINR(p.base_price)}
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </div>

        <DialogFooter className="px-6 py-4 border-t border-border shrink-0">
          <span className="text-sm text-muted-foreground mr-auto">
            {selected.size > 0 ? `${selected.size} selected` : ""}
          </span>
          <Button variant="outline" onClick={handleClose}>
            Cancel
          </Button>
          <Button
            onClick={handleConfirm}
            disabled={selected.size === 0 || loading}
            className="gap-2"
          >
            {loading && <Loader2 className="size-3.5 animate-spin" />}
            Add {selected.size > 0 ? `(${selected.size})` : ""}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function useDebounce<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value);
  useMemo(() => {
    const t = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return debounced;
}
