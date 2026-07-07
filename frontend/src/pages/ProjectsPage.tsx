import {
  Button,
  Dialog,
  DialogActions,
  DialogBody,
  DialogContent,
  DialogSurface,
  DialogTitle,
  DialogTrigger,
  Spinner,
  Text,
  Title2,
  Tooltip
} from "@fluentui/react-components";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy, Download, Trash2 } from "lucide-react";
import { useCallback, useState } from "react";

import {
  deleteProject,
  duplicateProject,
  exportProjectArchiveUrl,
  getProjects,
  type ProjectSummary
} from "../api/client";

export function ProjectsPage() {
  const queryClient = useQueryClient();
  const [pendingDelete, setPendingDelete] = useState<ProjectSummary | null>(null);
  const { data: projects, error, isLoading } = useQuery({
    queryKey: ["projects"],
    queryFn: getProjects
  });

  const onActionSuccess = useCallback(async () => {
    await queryClient.invalidateQueries({ queryKey: ["projects"] });
  }, [queryClient]);

  const duplicateMutation = useMutation({
    mutationFn: (projectId: string) => duplicateProject(projectId),
    onSuccess: () => void onActionSuccess()
  });

  const deleteMutation = useMutation({
    mutationFn: (projectId: string) => deleteProject(projectId),
    onSuccess: () => {
      setPendingDelete(null);
      void onActionSuccess();
    }
  });

  const handleExport = useCallback((projectId: string) => {
    window.open(exportProjectArchiveUrl(projectId), "_blank");
  }, []);

  if (isLoading) {
    return (
      <section className="page-surface" aria-label="Projects">
        <Spinner label="Loading projects" />
      </section>
    );
  }

  if (error) {
    return (
      <section className="page-surface" aria-label="Projects">
        <Title2 as="h2">Projects</Title2>
        <Text role="alert">Projects are unavailable.</Text>
      </section>
    );
  }

  return (
    <section className="page-surface" aria-label="Projects">
      <div className="section-heading">
        <Title2 as="h2">Projects</Title2>
        <Text className="muted-text">{projects?.length ?? 0} total</Text>
      </div>
      {projects?.length ? (
        <div className="item-grid">
          {projects.map((project) => (
            <article className="item-row project-row" key={project.id}>
              <div className="project-info">
                <Text weight="semibold">{project.name}</Text>
                <Text size={200} className="muted-text">
                  {project.id}
                </Text>
              </div>
              <div className="project-actions">
                <Tooltip content="Duplicate project" relationship="label">
                  <Button
                    appearance="subtle"
                    aria-label={`Duplicate ${project.name}`}
                    icon={
                      duplicateMutation.variables === project.id && duplicateMutation.isPending ? (
                        <Spinner size="tiny" />
                      ) : (
                        <Copy size={17} />
                      )
                    }
                    disabled={duplicateMutation.isPending}
                    onClick={() => duplicateMutation.mutate(project.id)}
                  />
                </Tooltip>
                <Tooltip content="Export archive" relationship="label">
                  <Button
                    appearance="subtle"
                    aria-label={`Export ${project.name}`}
                    icon={<Download size={17} />}
                    onClick={() => handleExport(project.id)}
                  />
                </Tooltip>
                <Tooltip content="Delete project" relationship="label">
                  <Button
                    appearance="subtle"
                    aria-label={`Delete ${project.name}`}
                    icon={<Trash2 size={17} />}
                    onClick={() => setPendingDelete(project)}
                  />
                </Tooltip>
              </div>
            </article>
          ))}
        </div>
      ) : (
        <div className="empty-state">
          <Text weight="semibold">No projects yet.</Text>
          <Text size={200} className="muted-text">
            The workspace is ready for the first project workflow.
          </Text>
        </div>
      )}

      <Dialog
        open={pendingDelete !== null}
        onOpenChange={(_event, data) => {
          if (!data.open) {
            setPendingDelete(null);
          }
        }}
      >
        <DialogSurface>
          <DialogBody>
            <DialogTitle>Delete project?</DialogTitle>
            <DialogContent>
              <Text>
                The project <strong>{pendingDelete?.name}</strong> and its revision history will be
                removed. This cannot be undone.
              </Text>
            </DialogContent>
            <DialogActions>
              <DialogTrigger>
                <Button appearance="secondary">Cancel</Button>
              </DialogTrigger>
              <Button
                appearance="primary"
                style={{ background: "var(--rs-danger)" }}
                disabled={deleteMutation.isPending}
                onClick={() => {
                  if (pendingDelete !== null) {
                    deleteMutation.mutate(pendingDelete.id);
                  }
                }}
              >
                {deleteMutation.isPending ? <Spinner size="tiny" /> : "Delete"}
              </Button>
            </DialogActions>
          </DialogBody>
        </DialogSurface>
      </Dialog>
    </section>
  );
}
