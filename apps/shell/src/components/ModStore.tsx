import {
  Check,
  Download,
  ExternalLink,
  LoaderCircle,
  PackageOpen,
  RefreshCw,
  Search,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  installStoreMod,
  listStoreMods,
  type ModStoreCatalog,
  type StoreMod,
} from "../api/store";

interface ModStoreProps {
  onInstalled: () => void | Promise<void>;
}

function installLabel(mod: StoreMod, installing: boolean) {
  if (installing) return "正在从 Git 安装";
  if (mod.installState === "installed") return "已安装";
  if (mod.installState === "update-available") return "从 Git 更新";
  return "从 Git 安装";
}

export function ModStore({ onInstalled }: ModStoreProps) {
  const [catalog, setCatalog] = useState<ModStoreCatalog>();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>();
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("全部");
  const [installingId, setInstallingId] = useState<string>();
  const [notice, setNotice] = useState<string>();

  const load = useCallback(async () => {
    setLoading(true);
    setError(undefined);
    try {
      setCatalog(await listStoreMods());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Mod 商店连接失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const categories = useMemo(
    () => [
      "全部",
      ...new Set((catalog?.mods ?? []).map((mod) => mod.category)),
    ],
    [catalog],
  );

  const visibleMods = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase("zh-CN");
    return (catalog?.mods ?? []).filter((mod) => {
      const categoryMatches = category === "全部" || mod.category === category;
      const queryMatches =
        !normalized ||
        [mod.name, mod.description, mod.publisher, ...mod.tags]
          .join(" ")
          .toLocaleLowerCase("zh-CN")
          .includes(normalized);
      return categoryMatches && queryMatches;
    });
  }, [catalog, category, query]);

  const install = async (mod: StoreMod) => {
    setInstallingId(mod.id);
    setError(undefined);
    setNotice(undefined);
    try {
      const action = await installStoreMod(mod.id);
      await Promise.all([load(), onInstalled()]);
      setNotice(
        action === "updated"
          ? `${mod.name} 已从 Git 更新。`
          : action === "unchanged"
            ? `${mod.name} 已是最新版本。`
            : `${mod.name} 已从 Git 安装并加入左侧导航。`,
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Git 安装失败");
    } finally {
      setInstallingId(undefined);
    }
  };

  return (
    <div className="mod-store-page">
      <header className="store-page-header">
        <div>
          <h1>Mod 商店</h1>
          <p>从项目官方 Git 商店按需安装功能，安装后会自动出现在左侧导航。</p>
        </div>
        {catalog ? (
          <a href={catalog.repository} target="_blank" rel="noreferrer">
            查看商店仓库
            <ExternalLink size={14} aria-hidden="true" />
          </a>
        ) : null}
      </header>

      {error ? (
        <div className="settings-notice settings-error" role="alert">
          <span>{error}</span>
          <button type="button" onClick={() => void load()}>
            <RefreshCw size={14} aria-hidden="true" />
            重试
          </button>
        </div>
      ) : null}
      {notice ? (
        <div className="settings-notice settings-success" role="status">
          <Check size={15} aria-hidden="true" />
          {notice}
        </div>
      ) : null}

      <section className="store-toolbar" aria-label="筛选 Mod">
        <label className="store-search">
          <Search size={15} aria-hidden="true" />
          <span className="sr-only">搜索 Mod</span>
          <input
            aria-label="搜索 Mod"
            placeholder="搜索名称、用途或标签"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>
        <label className="store-category-filter">
          <span>分类</span>
          <select
            aria-label="Mod 分类"
            value={category}
            onChange={(event) => setCategory(event.target.value)}
          >
            {categories.map((option) => (
              <option value={option} key={option}>{option}</option>
            ))}
          </select>
        </label>
        <span className="store-result-count">
          {catalog ? `${visibleMods.length} / ${catalog.mods.length} 个 Mod` : ""}
        </span>
      </section>

      {loading && !catalog ? (
        <div className="store-state" role="status">
          <LoaderCircle className="spin" size={20} aria-hidden="true" />
          正在读取项目商店…
        </div>
      ) : null}

      {!loading && catalog && visibleMods.length === 0 ? (
        <div className="store-state">
          <PackageOpen size={24} aria-hidden="true" />
          没有匹配的 Mod
        </div>
      ) : null}

      <div className="mod-store-grid">
        {visibleMods.map((mod) => {
          const installing = installingId === mod.id;
          const installed = mod.installState === "installed";
          return (
            <article className="store-mod-card" key={mod.id}>
              <div className="store-mod-heading">
                <span className="store-mod-icon" aria-hidden="true">
                  <PackageOpen size={17} />
                </span>
                <div>
                  <h2>{mod.name}</h2>
                  <span>{mod.version} · {mod.category}</span>
                </div>
                {mod.defaultInstall ? <small>内置 Mod</small> : null}
              </div>
              <p>{mod.description}</p>
              <div className="store-tag-list" aria-label={`${mod.name}标签`}>
                {mod.tags.map((tag) => <span key={tag}>{tag}</span>)}
              </div>
              <footer>
                <a href={mod.sourceUrl} target="_blank" rel="noreferrer">
                  Git 来源
                  <ExternalLink size={12} aria-hidden="true" />
                </a>
                <button
                  type="button"
                  className={installed ? "store-installed-button" : "store-install-button"}
                  aria-label={`${installLabel(mod, installing)} ${mod.name}`}
                  disabled={installed || installing || Boolean(installingId)}
                  onClick={() => void install(mod)}
                >
                  {installing ? (
                    <LoaderCircle className="spin" size={14} aria-hidden="true" />
                  ) : installed ? (
                    <Check size={14} aria-hidden="true" />
                  ) : (
                    <Download size={14} aria-hidden="true" />
                  )}
                  {installLabel(mod, installing)}
                </button>
              </footer>
            </article>
          );
        })}
      </div>
    </div>
  );
}
