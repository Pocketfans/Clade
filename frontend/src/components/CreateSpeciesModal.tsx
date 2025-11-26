import { useEffect, useState } from "react";
import { fetchSpeciesList, generateSpecies } from "../services/api";

interface Props {
  onClose: () => void;
  onSuccess: () => void;
}

export function CreateSpeciesModal({ onClose, onSuccess }: Props) {
  const [prompt, setPrompt] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [suggestedCode, setSuggestedCode] = useState<string>("");

  useEffect(() => {
    // 自动计算可用的 Lineage Code
    fetchSpeciesList()
      .then((list) => {
        const usedCodes = new Set(list.map((s) => s.lineage_code));
        // 简单的策略：尝试 X1, X2, ... Y1, Y2... 
        // 或者查找 A, B, C... 中还没使用的前缀
        const prefixes = "ABCDEFGHIJKLMNOPQRSTUVWXYZ".split("");
        
        // 找一个拥有最少物种的前缀，或者干脆找一个新的
        let bestPrefix = "S"; // S for Special
        
        // 检查 S1, S2...
        let index = 1;
        while (usedCodes.has(`${bestPrefix}${index}`)) {
          index++;
        }
        setSuggestedCode(`${bestPrefix}${index}`);
      })
      .catch(console.error);
  }, []);

  async function handleCreate() {
    if (!prompt.trim()) {
      setError("请输入物种描述");
      return;
    }
    if (!suggestedCode) {
      setError("正在计算编号，请稍候...");
      return;
    }

    setLoading(true);
    setError(null);

    try {
      await generateSpecies(prompt, suggestedCode);
      onSuccess();
      onClose();
    } catch (err: any) {
      console.error(err);
      setError(err.message || "生成失败");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="modal-backdrop">
      <div className="modal-window" style={{ maxWidth: "500px" }}>
        <div className="modal-header">
          <h3>创造新物种</h3>
          <button onClick={onClose} className="btn-icon">
            ×
          </button>
        </div>
        <div className="modal-body">
          <p className="text-tertiary text-sm mb-md">
            以上帝之手直接向当前生态系统注入一个全新的物种。它将获得编号 <strong>{suggestedCode}</strong>。
          </p>
          
          {error && (
            <div className="error-banner mb-md">
              {error}
            </div>
          )}

          <div className="form-group">
            <label className="form-label">物种描述</label>
            <textarea
              className="field-textarea"
              rows={5}
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="例如：一种体型巨大的陆行鸟类，拥有厚重的装甲以防御捕食者，主要以低矮灌木为食..."
            />
          </div>
        </div>
        <div className="modal-footer">
          <button onClick={onClose} className="btn btn-secondary" disabled={loading}>
            取消
          </button>
          <button onClick={handleCreate} className="btn btn-primary" disabled={loading}>
            {loading ? "生成中..." : "确认创造"}
          </button>
        </div>
      </div>
    </div>
  );
}

