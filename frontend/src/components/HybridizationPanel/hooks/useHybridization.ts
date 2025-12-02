/**
 * useHybridization - 杂交数据管理 Hook
 */

import { useState, useCallback, useEffect } from "react";
import type {
  HybridCandidate,
  HybridPreview,
  ForceHybridPreview,
  AllSpecies,
  HybridMode,
} from "../types";

interface UseHybridizationResult {
  // 模式
  mode: HybridMode;
  setMode: (mode: HybridMode) => void;

  // 普通杂交
  candidates: HybridCandidate[];
  selectedPair: HybridCandidate | null;
  preview: HybridPreview | null;
  setSelectedPair: (pair: HybridCandidate | null) => void;

  // 强行杂交
  allSpecies: AllSpecies[];
  forceSpeciesA: AllSpecies | null;
  forceSpeciesB: AllSpecies | null;
  forcePreview: ForceHybridPreview | null;
  setForceSpeciesA: (species: AllSpecies | null) => void;
  setForceSpeciesB: (species: AllSpecies | null) => void;

  // 状态
  loading: boolean;
  executing: boolean;
  previewLoading: boolean;
  error: string | null;
  success: string | null;

  // 操作
  fetchCandidates: () => Promise<void>;
  fetchPreview: (codeA: string, codeB: string) => Promise<void>;
  fetchForcePreview: (codeA: string, codeB: string) => Promise<void>;
  executeHybrid: (codeA: string, codeB: string) => Promise<boolean>;
  executeForceHybrid: (codeA: string, codeB: string) => Promise<boolean>;
  clearError: () => void;
  clearSuccess: () => void;
}

export function useHybridization(): UseHybridizationResult {
  const [mode, setMode] = useState<HybridMode>("normal");

  // 普通杂交状态
  const [candidates, setCandidates] = useState<HybridCandidate[]>([]);
  const [selectedPair, setSelectedPair] = useState<HybridCandidate | null>(null);
  const [preview, setPreview] = useState<HybridPreview | null>(null);

  // 强行杂交状态
  const [allSpecies, setAllSpecies] = useState<AllSpecies[]>([]);
  const [forceSpeciesA, setForceSpeciesA] = useState<AllSpecies | null>(null);
  const [forceSpeciesB, setForceSpeciesB] = useState<AllSpecies | null>(null);
  const [forcePreview, setForcePreview] = useState<ForceHybridPreview | null>(null);

  // 通用状态
  const [loading, setLoading] = useState(false);
  const [executing, setExecuting] = useState(false);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // 获取杂交候选
  const fetchCandidates = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/hybridization/candidates");
      if (!res.ok) throw new Error("获取杂交候选失败");
      const data = await res.json();
      setCandidates(data.candidates || []);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "操作失败");
    } finally {
      setLoading(false);
    }
  }, []);

  // 获取所有物种（用于强行杂交）
  const fetchAllSpecies = useCallback(async () => {
    try {
      const res = await fetch("/api/species/list");
      if (!res.ok) throw new Error("获取物种列表失败");
      const data = await res.json();
      setAllSpecies(data.species?.filter((s: AllSpecies) => s.status === "alive") || []);
    } catch (err: unknown) {
      console.error("获取物种列表失败:", err);
    }
  }, []);

  // 获取杂交预览
  const fetchPreview = useCallback(async (codeA: string, codeB: string) => {
    setPreviewLoading(true);
    setPreview(null);
    try {
      const res = await fetch("/api/hybridization/preview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ species_a: codeA, species_b: codeB }),
      });
      if (!res.ok) throw new Error("获取预览失败");
      const data = await res.json();
      setPreview(data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "操作失败");
    } finally {
      setPreviewLoading(false);
    }
  }, []);

  // 获取强行杂交预览
  const fetchForcePreview = useCallback(async (codeA: string, codeB: string) => {
    setPreviewLoading(true);
    setForcePreview(null);
    try {
      const res = await fetch("/api/hybridization/force/preview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ species_a: codeA, species_b: codeB }),
      });
      if (!res.ok) throw new Error("获取预览失败");
      const data = await res.json();
      setForcePreview(data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "操作失败");
    } finally {
      setPreviewLoading(false);
    }
  }, []);

  // 执行杂交
  const executeHybrid = useCallback(async (codeA: string, codeB: string): Promise<boolean> => {
    setExecuting(true);
    setError(null);
    try {
      const res = await fetch("/api/hybridization/execute", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ species_a: codeA, species_b: codeB }),
      });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || "杂交失败");
      }
      const data = await res.json();
      setSuccess(`杂交成功！新物种：${data.hybrid?.common_name || "未知"}`);
      return true;
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "操作失败");
      return false;
    } finally {
      setExecuting(false);
    }
  }, []);

  // 执行强行杂交
  const executeForceHybrid = useCallback(async (codeA: string, codeB: string): Promise<boolean> => {
    setExecuting(true);
    setError(null);
    try {
      const res = await fetch("/api/hybridization/force/execute", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ species_a: codeA, species_b: codeB }),
      });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || "强行杂交失败");
      }
      const data = await res.json();
      setSuccess(`强行杂交成功！创造嵌合体：${data.hybrid?.common_name || "未知"}`);
      return true;
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "操作失败");
      return false;
    } finally {
      setExecuting(false);
    }
  }, []);

  const clearError = useCallback(() => setError(null), []);
  const clearSuccess = useCallback(() => setSuccess(null), []);

  // 初始化加载
  useEffect(() => {
    fetchCandidates();
    fetchAllSpecies();
  }, [fetchCandidates, fetchAllSpecies]);

  // 选择候选时自动获取预览
  useEffect(() => {
    if (selectedPair) {
      fetchPreview(selectedPair.species_a.lineage_code, selectedPair.species_b.lineage_code);
    }
  }, [selectedPair, fetchPreview]);

  // 强行杂交选择时自动获取预览
  useEffect(() => {
    if (forceSpeciesA && forceSpeciesB) {
      fetchForcePreview(forceSpeciesA.lineage_code, forceSpeciesB.lineage_code);
    }
  }, [forceSpeciesA, forceSpeciesB, fetchForcePreview]);

  return {
    mode,
    setMode,
    candidates,
    selectedPair,
    preview,
    setSelectedPair,
    allSpecies,
    forceSpeciesA,
    forceSpeciesB,
    forcePreview,
    setForceSpeciesA,
    setForceSpeciesB,
    loading,
    executing,
    previewLoading,
    error,
    success,
    fetchCandidates,
    fetchPreview,
    fetchForcePreview,
    executeHybrid,
    executeForceHybrid,
    clearError,
    clearSuccess,
  };
}

