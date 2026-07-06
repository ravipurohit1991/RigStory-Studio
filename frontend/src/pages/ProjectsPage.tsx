import { Spinner, Text, Title2 } from "@fluentui/react-components";
import { useQuery } from "@tanstack/react-query";

import { getProjects } from "../api/client";

export function ProjectsPage() {
  const { data: projects, error, isLoading } = useQuery({
    queryKey: ["projects"],
    queryFn: getProjects
  });

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
            <article className="item-row" key={project.id}>
              <Text weight="semibold">{project.name}</Text>
              <Text size={200} className="muted-text">
                {project.id}
              </Text>
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
    </section>
  );
}
