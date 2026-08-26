import { useEffect, useState, type FormEvent } from "react";
import { Bot, Database, KeyRound, Loader2, Save } from "lucide-react";
import { toast } from "sonner";
import { QVerisSettings } from "@/components/settings/QVerisSettings";
import { api, type DataSourceSettings } from "@/lib/api";
import { openVibeDeskCopilot } from "@/lib/vibedesk";

const fieldClass =
  "w-full rounded-md border bg-background px-3 py-2 text-sm outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/20 disabled:cursor-not-allowed disabled:opacity-60";

export function IntegratedSettings() {
  const [settings, setSettings] = useState<DataSourceSettings | null>(null);
  const [token, setToken] = useState("");
  const [clearToken, setClearToken] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    api.getDataSourceSettings()
      .then((value) => {
        if (active) setSettings(value);
      })
      .catch((reason) => {
        if (active) setError(reason instanceof Error ? reason.message : "设置加载失败");
      });
    return () => {
      active = false;
    };
  }, []);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setSaving(true);
    try {
      const value = await api.updateDataSourceSettings({
        tushare_token: token.trim() || undefined,
        clear_tushare_token: clearToken,
      });
      setSettings(value);
      setToken("");
      setClearToken(false);
      toast.success("数据源设置已保存");
    } catch (reason) {
      toast.error(reason instanceof Error ? reason.message : "保存失败");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="mx-auto max-w-5xl space-y-6 p-6">
      <header className="space-y-2" data-mod-page-title>
        <h1 className="text-2xl font-semibold tracking-tight">量化系统设置</h1>
        <p className="max-w-3xl text-sm text-muted-foreground">
          Vibe Trading 只保留量化数据与运行配置；模型、会话和工具选择统一继承 Newma-Desk Agent。
        </p>
      </header>

      <section className="rounded-lg border bg-card p-5 shadow-sm">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-start gap-3">
            <Bot className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
            <div className="space-y-1">
              <h2 className="font-semibold">统一 Agent 已接管</h2>
              <p className="text-sm text-muted-foreground">
                此 Mod 不再保存独立模型密钥，也不会启动原生 Agent、频道或会话进程。
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => void openVibeDeskCopilot()}
            className="shrink-0 rounded-md border px-3 py-2 text-sm font-medium transition hover:bg-muted"
          >
            打开 Desk Agent
          </button>
        </div>
      </section>

      <QVerisSettings />

      <form onSubmit={submit} className="rounded-lg border bg-card p-5 shadow-sm">
        <div className="mb-5 flex items-start gap-3">
          <Database className="mt-0.5 h-4 w-4 text-primary" />
          <div>
            <h2 className="font-semibold">行情数据源</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              可选配置 Tushare；未配置时使用已启用的免密数据 Adapter。
            </p>
          </div>
        </div>

        {error ? (
          <div className="rounded-md border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
            {error}
          </div>
        ) : !settings ? (
          <div className="flex min-h-24 items-center justify-center text-sm text-muted-foreground">
            <Loader2 className="mr-2 h-4 w-4 animate-spin" /> 正在加载…
          </div>
        ) : (
          <div className="grid gap-4">
            <label className="grid gap-2">
              <span className="text-sm font-medium">Tushare Token</span>
              <div className="relative">
                <KeyRound className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
                <input
                  type="password"
                  value={token}
                  onChange={(event) => setToken(event.target.value)}
                  className={`${fieldClass} pl-9`}
                  placeholder={settings.tushare_token_configured ? "已配置；留空保持不变" : "可选"}
                  disabled={clearToken}
                  autoComplete="current-password"
                />
              </div>
            </label>
            <label className="flex items-center gap-2 text-xs text-muted-foreground">
              <input
                type="checkbox"
                checked={clearToken}
                onChange={(event) => {
                  setClearToken(event.target.checked);
                  if (event.target.checked) setToken("");
                }}
                className="h-3.5 w-3.5 accent-primary"
              />
              清除已保存的 Tushare Token
            </label>
            <div className="rounded-md border bg-muted/20 p-3 text-xs text-muted-foreground">
              BaoStock：{settings.baostock_message}
            </div>
            <button
              type="submit"
              disabled={saving}
              className="inline-flex w-fit items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-60"
            >
              {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
              保存数据源
            </button>
          </div>
        )}
      </form>
    </div>
  );
}
