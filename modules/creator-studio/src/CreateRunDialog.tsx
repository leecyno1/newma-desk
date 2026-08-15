import { Plus, X } from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";

import type { CreatorMaterial, CreatorRegistry } from "./types";

interface MaterialDraft extends CreatorMaterial {
  required?: boolean;
  hint?: string;
}

export function CreateRunDialog({
  registry,
  busy,
  onClose,
  onCreate,
}: {
  registry: CreatorRegistry;
  busy: boolean;
  onClose(): void;
  onCreate(input: {
    title: string;
    stageId: string;
    nodeId: string;
    materials: CreatorMaterial[];
  }): Promise<unknown>;
}) {
  const firstStage = registry.stages[0];
  const [title, setTitle] = useState("");
  const [stageId, setStageId] = useState(firstStage?.id ?? "");
  const selectedStage = useMemo(
    () => registry.stages.find((stage) => stage.id === stageId) ?? firstStage,
    [firstStage, registry.stages, stageId],
  );
  const [nodeId, setNodeId] = useState(selectedStage?.nodes[0]?.id ?? "");
  const selectedNode = useMemo(
    () => selectedStage?.nodes.find((node) => node.id === nodeId) ?? selectedStage?.nodes[0],
    [nodeId, selectedStage],
  );
  const [materials, setMaterials] = useState<MaterialDraft[]>([]);

  useEffect(() => {
    if (!selectedStage?.nodes.some((node) => node.id === nodeId)) {
      setNodeId(selectedStage?.nodes[0]?.id ?? "");
    }
  }, [nodeId, selectedStage]);

  useEffect(() => {
    setMaterials((selectedNode?.material_requirements ?? []).map((requirement) => ({
      type: requirement.type,
      path: "",
      source: "manual",
      label: requirement.label,
      required: requirement.required,
      hint: (requirement.accepts ?? []).join(" / "),
    })));
  }, [selectedNode?.id]);

  const updateMaterial = (index: number, next: Partial<MaterialDraft>) => {
    setMaterials((current) => current.map((item, itemIndex) => (
      itemIndex === index ? { ...item, ...next } : item
    )));
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    await onCreate({
      title: title.trim(),
      stageId,
      nodeId,
      materials: materials
        .filter((material) => material.path.trim())
        .map(({ required: _required, hint: _hint, ...material }) => material),
    });
  };

  return (
    <div className="creator-dialog-backdrop" role="presentation" onMouseDown={onClose}>
      <form className="creator-dialog" onSubmit={(event) => void submit(event)} onMouseDown={(event) => event.stopPropagation()}>
        <header>
          <div>
            <span className="eyebrow">NEW RUN</span>
            <h2>从任意节点新建任务</h2>
            <p>先选节点，再提供满足当前节点要求的素材。</p>
          </div>
          <button type="button" className="icon-button" onClick={onClose} aria-label="关闭">
            <X size={18} />
          </button>
        </header>

        <label className="field">
          <span>任务名称</span>
          <input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="例如：DeepSeek 涨价背后的大模型生态" autoFocus />
        </label>

        <div className="form-grid">
          <label className="field">
            <span>起始阶段</span>
            <select value={stageId} onChange={(event) => setStageId(event.target.value)}>
              {registry.stages.map((stage) => <option value={stage.id} key={stage.id}>{stage.order}. {stage.name}</option>)}
            </select>
          </label>
          <label className="field">
            <span>起始节点</span>
            <select value={nodeId} onChange={(event) => setNodeId(event.target.value)}>
              {selectedStage?.nodes.map((node) => <option value={node.id} key={node.id}>{node.name}</option>)}
            </select>
          </label>
        </div>

        <section className="material-builder">
          <div className="section-heading compact">
            <div><span>材料契约</span><h3>{selectedNode?.name}</h3></div>
            <small>{materials.filter((item) => item.required).length} 项必需</small>
          </div>
          {materials.length === 0 ? <p className="quiet-card">当前节点无需前置素材，可直接创建。</p> : materials.map((material, index) => (
            <div className="material-draft-row" key={material.type + String(index)}>
              <div>
                <strong>{material.label || material.type}{material.required ? " *" : ""}</strong>
                <small>{material.type}{material.hint ? " · " + material.hint : ""}</small>
              </div>
              <input
                value={material.path}
                onChange={(event) => updateMaterial(index, { path: event.target.value })}
                placeholder="文件路径或 URL"
                required={material.required}
              />
            </div>
          ))}
          <button
            type="button"
            className="text-button"
            onClick={() => setMaterials((current) => [...current, { type: "file", path: "", source: "manual", label: "补充素材" }])}
          >
            <Plus size={14} />增加补充素材
          </button>
        </section>

        <footer>
          <button type="button" className="secondary-button" onClick={onClose}>取消</button>
          <button className="primary-button" disabled={busy || !title.trim() || !stageId || !nodeId}>
            {busy ? "正在创建…" : "创建并进入节点"}
          </button>
        </footer>
      </form>
    </div>
  );
}
