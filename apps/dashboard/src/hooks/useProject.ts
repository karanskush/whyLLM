"use client";

import { useCallback, useEffect, useState } from "react";

const STORAGE_KEY = "whyllm_active_project_id";

/**
 * Reads and writes the active project ID from localStorage.
 * Used by all dashboard pages instead of the incorrect orgId fallback.
 */
export function useProject() {
  const [projectId, setProjectIdState] = useState<string | null>(null);

  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) setProjectIdState(stored);
  }, []);

  const setProjectId = useCallback((id: string) => {
    localStorage.setItem(STORAGE_KEY, id);
    setProjectIdState(id);
  }, []);

  const clearProject = useCallback(() => {
    localStorage.removeItem(STORAGE_KEY);
    setProjectIdState(null);
  }, []);

  return { projectId, setProjectId, clearProject };
}
