import { useMutation } from "@tanstack/react-query";
import { RotateCcw } from "lucide-react";
import { errorMessage, post, refreshWorkspace, useWorkspace } from "../api";
import { label } from "../lib/format";
import type { Run } from "../types";
import { Spinner } from "./ui";
import { useToast } from "./notifications";

export function SearchReport({ run }: { run: Run }) {
  const notify = useToast();
  const workspace = useWorkspace();
  const retry = useMutation({
    mutationFn: () => post("/discover", { retry_run_id: run.id }),
    onSuccess: async () => {
      await refreshWorkspace();
      notify("Incomplete searches queued for retry.");
    },
    onError: (error) => notify(errorMessage(error), "error"),
  });
  const queries = Object.entries(run.stats.coverage || {}).flatMap(
    ([source, entries]) => entries.map((entry) => ({ source, ...entry })),
  );
  const incomplete =
    queries.some((entry) => entry.status !== "complete") ||
    !!Object.keys(run.stats.failures || {}).length;
  return (
    <>
      {!!Object.keys(run.stats.quality || {}).length && (
        <div className="workflow-table-scroll">
          <table className="workflow-table">
            <caption>Source quality for this run</caption>
            <thead>
              <tr>
                <th>Source</th>
                <th>Fetched</th>
                <th>Detailed</th>
                <th>Recommended</th>
                <th>New</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(run.stats.quality || {}).map(([key, quality]) => (
                <tr key={key}>
                  <td>{label(key)}</td>
                  <td>{quality.fetched}</td>
                  <td>{quality.full_description}</td>
                  <td>{quality.relevant}</td>
                  <td>{quality.new}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {!!queries.length && (
        <div className="workflow-table-scroll">
          <table className="workflow-table">
            <caption>Query coverage</caption>
            <thead>
              <tr>
                <th>Source / role</th>
                <th>Location</th>
                <th>Outcome</th>
                <th>Postings</th>
              </tr>
            </thead>
            <tbody>
              {queries.map((query, index) => (
                <tr key={index}>
                  <td>
                    {label(query.source)}
                    <br />
                    {query.query || "Latest postings"}
                  </td>
                  <td>{query.location || "All locations"}</td>
                  <td className={`status-${query.status}`}>
                    {label(query.status)}
                    {query.reason && <p>{query.reason}</p>}
                  </td>
                  <td>{query.count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {incomplete && (
        <button
          className="button secondary small"
          disabled={
            retry.isPending ||
            workspace.data?.tasks.some((task) => task.kind === "search")
          }
          onClick={() => retry.mutate()}
        >
          {retry.isPending ? <Spinner /> : <RotateCcw size={15} />}Retry
          incomplete searches
        </button>
      )}
    </>
  );
}
