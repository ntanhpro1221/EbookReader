import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Download, Laptop, Loader2, RefreshCw, Search, Unplug, Wifi } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { BookCover } from "@/shared/BookCover";
import { cn } from "@/shared/cn";
import { formatLength } from "@/shared/format";
import { Button, EmptyState, Progress } from "@/shared/ui";
import { EbookLibrary, type DownloadEvent, type RemoteBook } from "./plugins";

// "Tải sách": lấy sách từ máy tính qua Wi-Fi. Ghép nối một lần bằng mã 6 số hiện trong Cài đặt của máy tính;
// sau đó chỉ cần mở màn hình này để thấy sách mới và chương mới.

function formatBytes(bytes: number): string {
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toLocaleString("vi-VN", { maximumFractionDigits: 1 })} GB`;
  return `${Math.round(bytes / 1024 ** 2).toLocaleString("vi-VN")} MB`;
}

function PairPanel() {
  const client = useQueryClient();
  const [computers, setComputers] = useState<{ host: string; port: number; name: string }[] | null>(null);
  const [target, setTarget] = useState<{ host: string; port: number; name: string } | null>(null);
  const [manual, setManual] = useState(false);
  const [address, setAddress] = useState("");
  const [code, setCode] = useState("");
  const discover = useMutation({
    mutationFn: () => EbookLibrary.discover({ timeoutMs: 2500 }),
    onSuccess: ({ computers: found }) => {
      setComputers(found);
      if (found.length === 1) setTarget(found[0]);
    },
  });
  const pair = useMutation({
    mutationFn: () => {
      const host = target?.host ?? address.split(":")[0].trim();
      const port = target?.port ?? Number(address.split(":")[1] ?? 47630);
      return EbookLibrary.pair({ host, port, code: code.replace(/\D/g, "") });
    },
    onSuccess: ({ name }) => {
      toast.success(`Đã kết nối với ${name}`);
      void client.invalidateQueries({ queryKey: ["connection"] });
    },
    onError: (error: Error) => toast.error("Chưa kết nối được", { description: error.message }),
  });
  useEffect(() => {
    discover.mutate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const ready = (target || address.includes(".")) && code.replace(/\D/g, "").length === 6;
  return (
    <div className="space-y-5">
      <div className="rounded-2xl border border-line bg-panel p-5">
        <div className="flex items-center gap-3">
          <div className="grid size-11 place-items-center rounded-xl bg-accent-soft text-accent-text">
            <Wifi className="size-5" />
          </div>
          <div>
            <h2 className="font-semibold">Kết nối với máy tính</h2>
            <p className="text-sm text-fg-2">Điện thoại và máy tính cần cùng một mạng Wi-Fi.</p>
          </div>
        </div>
        <ol className="mt-4 space-y-1.5 text-sm text-fg-2">
          <li>1. Trên máy tính: mở Ebook Reader → Cài đặt → bật “Cho phép điện thoại kết nối”.</li>
          <li>2. Chọn máy tính bên dưới và nhập mã 6 số đang hiện ở đó.</li>
        </ol>
      </div>

      {!manual && (
        <div>
          <div className="mb-2 flex items-center justify-between">
            <span className="text-sm font-semibold">Máy tính tìm thấy</span>
            <button type="button" onClick={() => discover.mutate()} className="flex items-center gap-1.5 text-sm text-accent-text">
              {discover.isPending ? <Loader2 className="size-4 animate-spin" /> : <Search className="size-4" />} Tìm lại
            </button>
          </div>
          {computers?.length ? (
            <div className="space-y-2">
              {computers.map((computer) => (
                <button
                  key={computer.host}
                  type="button"
                  onClick={() => setTarget(computer)}
                  className={cn(
                    "flex w-full items-center gap-3 rounded-xl border p-3.5 text-left",
                    target?.host === computer.host ? "border-accent bg-accent-soft" : "border-line bg-panel",
                  )}
                >
                  <Laptop className="size-5 text-fg-2" />
                  <span className="flex-1">
                    <span className="block font-medium">{computer.name}</span>
                    <span className="block text-xs text-fg-2">{computer.host}</span>
                  </span>
                  {target?.host === computer.host && <CheckCircle2 className="size-5 text-accent-text" />}
                </button>
              ))}
            </div>
          ) : (
            <p className="rounded-xl bg-hover px-4 py-3 text-sm text-fg-2">
              {discover.isPending ? "Đang tìm trong mạng Wi-Fi…" : "Chưa thấy máy tính nào. Kiểm tra máy tính đã bật kết nối, hoặc nhập địa chỉ."}
            </p>
          )}
        </div>
      )}

      <button type="button" onClick={() => { setManual((value) => !value); setTarget(null); }} className="text-sm font-medium text-fg-2 underline underline-offset-4">
        {manual ? "Tự tìm máy tính" : "Nhập địa chỉ máy tính"}
      </button>
      {manual && (
        <input
          value={address}
          onChange={(event) => setAddress(event.target.value)}
          inputMode="url"
          placeholder="Ví dụ 192.168.1.20:47630"
          className="h-12 w-full rounded-xl border border-line bg-panel px-4 text-base outline-none focus:border-accent"
        />
      )}

      <label className="block">
        <span className="text-sm font-semibold">Mã ghép nối</span>
        <input
          value={code}
          onChange={(event) => setCode(event.target.value.replace(/\D/g, "").slice(0, 6))}
          inputMode="numeric"
          autoComplete="one-time-code"
          placeholder="••••••"
          className="tabular mt-1.5 h-14 w-full rounded-xl border border-line bg-panel text-center text-2xl font-semibold tracking-[0.5em] outline-none focus:border-accent"
        />
      </label>
      <Button variant="primary" size="lg" className="w-full" disabled={!ready} loading={pair.isPending} onClick={() => pair.mutate()}>
        Kết nối
      </Button>
    </div>
  );
}

function RemoteRow({ book, progress, onDownload }: { book: RemoteBook; progress?: DownloadEvent; onDownload: () => void }) {
  const newChapters = book.downloaded ? book.chaptersAvailable - book.localChapters : 0;
  const downloading = progress && !progress.finished && !progress.error;
  const fraction = progress?.total ? (progress.done ?? 0) / progress.total : (progress?.files ?? 0) / Math.max(1, progress?.filesTotal ?? 1);
  return (
    <div className="flex items-center gap-3 py-3">
      <BookCover title={book.title} size="sm" className="size-14" />
      <div className="min-w-0 flex-1">
        <div className="truncate font-semibold">{book.title}</div>
        <div className="text-xs text-fg-2">
          {book.chaptersAvailable}/{book.chaptersTotal} chương · {formatLength(book.duration)}
          {!book.complete && " · đang làm"}
        </div>
        {downloading && <Progress value={fraction} running size="xs" className="mt-2" />}
      </div>
      {downloading ? (
        <span className="tabular w-12 text-right text-xs font-semibold text-accent-text">{Math.round(fraction * 100)}%</span>
      ) : book.downloaded && newChapters <= 0 ? (
        <span className="flex items-center gap-1 text-xs text-success">
          <CheckCircle2 className="size-4" /> Đã tải
        </span>
      ) : (
        <Button size="sm" variant={book.downloaded ? "secondary" : "primary"} icon={Download} onClick={onDownload}>
          {book.downloaded ? `+${newChapters} chương` : "Tải"}
        </Button>
      )}
    </div>
  );
}

export function DevicesScreen() {
  const client = useQueryClient();
  const connection = useQuery({ queryKey: ["connection"], queryFn: () => EbookLibrary.connection() });
  const remote = useQuery({
    queryKey: ["remote"],
    enabled: Boolean(connection.data?.paired),
    queryFn: () => EbookLibrary.remoteLibrary(),
    retry: 0,
  });
  const storage = useQuery({ queryKey: ["storage"], queryFn: () => EbookLibrary.storage() });
  const [progress, setProgress] = useState<Record<string, DownloadEvent>>({});

  useEffect(() => {
    const handle = EbookLibrary.addListener("download", (event) => {
      setProgress((current) => ({ ...current, [event.bookId]: event }));
      if (event.finished) {
        toast.success("Đã tải xong", { description: "Sách đã có trong Thư viện, nghe được cả khi không có mạng." });
        void client.invalidateQueries({ queryKey: ["remote"] });
        void client.invalidateQueries({ queryKey: ["listen"] });
        void client.invalidateQueries({ queryKey: ["storage"] });
      }
      if (event.error) toast.error("Tải bị gián đoạn", { description: event.error });
    });
    return () => void handle.then((listener) => listener.remove());
  }, [client]);

  const unpair = async () => {
    await EbookLibrary.unpair();
    void client.invalidateQueries({ queryKey: ["connection"] });
  };

  return (
    <div className="px-4 pb-8 pt-4">
      <h1 className="text-2xl font-bold tracking-tight">Tải sách</h1>
      <div className="mt-5">
        {!connection.data?.paired ? (
          <PairPanel />
        ) : (
          <>
            <div className="flex items-center gap-3 rounded-2xl border border-line bg-panel p-4">
              <Laptop className="size-5 text-fg-2" />
              <div className="min-w-0 flex-1">
                <div className="truncate font-semibold">{connection.data.name || connection.data.host}</div>
                <div className={cn("text-xs", remote.isError ? "text-danger" : "text-fg-2")}>
                  {remote.isError ? "Không kết nối được - máy tính đang tắt hoặc khác mạng Wi-Fi" : "Đã kết nối"}
                </div>
              </div>
              <button type="button" aria-label="Làm mới" onClick={() => void remote.refetch()} className="grid size-10 place-items-center rounded-full text-fg-2">
                <RefreshCw className={cn("size-4", remote.isFetching && "animate-spin")} />
              </button>
            </div>
            <div className="mt-5 divide-y divide-line">
              {remote.data?.books.length ? (
                remote.data.books.map((book) => (
                  <RemoteRow
                    key={book.id}
                    book={book}
                    progress={progress[book.id]}
                    onDownload={() => void EbookLibrary.download({ bookId: book.id }).catch(() => undefined)}
                  />
                ))
              ) : remote.isLoading ? (
                <p className="py-6 text-center text-sm text-fg-2">Đang lấy danh sách sách…</p>
              ) : (
                <EmptyState icon={Download} title="Máy tính chưa có sách nghe được" className="py-8">
                  Sách hiện ở đây ngay khi chương đầu tiên được thu xong trên máy tính.
                </EmptyState>
              )}
            </div>
            <button type="button" onClick={() => void unpair()} className="mt-6 flex items-center gap-2 text-sm text-fg-2">
              <Unplug className="size-4" /> Ngắt kết nối với máy tính này
            </button>
          </>
        )}
      </div>
      {storage.data && (
        <p className="mt-8 text-center text-xs text-fg-3">
          Sách trên máy: {formatBytes(storage.data.bytes)} · còn trống {formatBytes(storage.data.free)}
        </p>
      )}
    </div>
  );
}
