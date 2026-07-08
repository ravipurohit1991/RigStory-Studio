import {
  Button,
  Dialog,
  DialogActions,
  DialogBody,
  DialogContent,
  DialogSurface,
  DialogTitle,
  DialogTrigger,
  Input,
  Spinner,
  Text,
  Title2,
  Tooltip
} from "@fluentui/react-components";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy, Download, Search, SearchX, Trash2, X } from "lucide-react";
import { useCallback, useMemo, useState } from "react";

import {
  deleteProject,
  duplicateProject,
  exportProjectArchiveUrl,
  getProjects,
  type ProjectSummary
} from "../api/client";

const SEARCH_PLACEHOLDER = "Filter projects by name or ID";
const SEARCH_INPUT_LABEL = "Filter projects";
const SEARCH_CLEAR_LABEL = "Clear search";
const EMPTY_STATE_CLEAR_LABEL = "Clear filter";

function normalize(value: string): string {
  return value.trim().toLowerCase();
}

function matchesQuery(project: ProjectSummary, query: string): boolean {
  if (query === "") {
    return true;
  }
  return (
    project.name.toLowerCase().includes(query) || project.id.toLowerCase().includes(query)
  );
}

export function ProjectsPage() {
  const queryClient = useQueryClient();
  const [pendingDelete, setPendingDelete] = useState<ProjectSummary | null>(null);
  const [searchValue, setSearchValue] = useState("");
  const { data: projects, error, isLoading } = useQuery({
    queryKey: ["projects"],
    queryFn: getProjects
  });

  const normalizedQuery = useMemo(() => normalize(searchValue), [searchValue]);
  const filteredProjects = useMemo(() => {
    if (!projects) {
      return undefined;
    }
    return projects.filter((project) => matchesQuery(project, normalizedQuery));
  }, [projects, normalizedQuery]);

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

  const handleSearchChange = useCallback(
    (_event: unknown, data: { value: string }) => {
      setSearchValue(data.value);
      if (pendingDelete !== null) {
        setPendingDelete(null);
      }
    },
    [pendingDelete]
  );

  const handleClearSearch = useCallback(() => {
    setSearchValue("");
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

  const totalCount = projects?.length ?? 0;
  const visibleCount = filteredProjects?.length ?? 0;
  const isFiltered = normalizedQuery !== "" && totalCount > 0;
  const counterLabel = isFiltered
    ? `${visibleCount} of ${totalCount}`
    : `${totalCount} total`;

  return (
    <section className="page-surface" aria-label="Projects">
      <div className="section-heading">
        <div className="projects-heading-text">
          <Title2 as="h2">Projects</Title2>
          <Text className="muted-text" aria-live="polite">
            {counterLabel}
          </Text>
        </div>
        <div className="project-search">
          <Input
            className="project-search-input"
            type="search"
            aria-label={SEARCH_INPUT_LABEL}
            placeholder={SEARCH_PLACEHOLDER}
            value={searchValue}
            onChange={handleSearchChange}
            contentBefore={<SearchGlyph />}
            contentAfter={
              searchValue === "" ? null : (
                <Tooltip content={SEARCH_CLEAR_LABEL} relationship="label">
                  <Button
                    appearance="subtle"
                    size="small"
                    aria-label={SEARCH_CLEAR_LABEL}
                    icon={<X size={14} />}
                    onClick={handleClearSearch}
                  />
                </Tooltip>
              )
            }
          />
        </div>
      </div>

      {visibleCount > 0 ? (
        <div className="item-grid">
          {filteredProjects?.map((project) => (
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
      ) : totalCount === 0 ? (
        <div className="empty-state">
          <Text weight="semibold">No projects yet.</Text>
          <Text size={200} className="muted-text">
            The workspace is ready for the first project workflow.
          </Text>
        </div>
      ) : (
        <div className="empty-state" role="status">
          <SearchX size={28} aria-hidden="true" />
          <Text weight="semibold">No projects match &ldquo;{searchValue.trim()}&rdquo;.</Text>
          <Text size={200} className="muted-text">
            Adjust the filter or clear it to see all {totalCount} projects.
          </Text>
          <Button appearance="secondary" aria-label={EMPTY_STATE_CLEAR_LABEL} onClick={handleClearSearch}>
            Clear filter
          </Button>
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

function SearchGlyph() {
  return (
    <span aria-hidden="true" className="project-search-glyph">
      <Search size={16} />
    </span>
  );
}
