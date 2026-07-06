import {
  Badge,
  Body1,
  Table,
  TableBody,
  TableCell,
  TableHeader,
  TableHeaderCell,
  TableRow,
  Text,
  Title3
} from "@fluentui/react-components";
import { useMemo } from "react";

import bipedProjectJson from "@samples/projects/biped-demo.rigstory.json";
import { computeBoneEndpoints, validateRig, type ValidationIssue } from "../engine/rig";
import { validateProjectDocument } from "../schemas/invariants";
import { projectDocumentSchema } from "../schemas/project";

interface EndpointRow {
  boneId: string;
  origin: string;
  tip: string;
}

interface FixtureReport {
  projectName: string;
  schemaVersion: string;
  characterCount: number;
  sceneCount: number;
  clipCount: number;
  boneCount: number;
  attachmentCount: number;
  projectIssues: ValidationIssue[];
  rigIssues: ValidationIssue[];
  endpointRows: EndpointRow[];
}

function formatPoint(x: number, y: number): string {
  return `(${x.toFixed(3)}, ${y.toFixed(3)})`;
}

function buildReport(): FixtureReport {
  const document = projectDocumentSchema.parse(bipedProjectJson);
  const projectIssues = validateProjectDocument(document);
  const character = document.characters[0];
  const rigIssues = validateRig(character.rig);
  const endpointRows: EndpointRow[] = [];
  if (rigIssues.length === 0) {
    const endpoints = computeBoneEndpoints(character.rig);
    for (const bone of character.rig.bones) {
      const endpoint = endpoints.get(bone.id);
      if (endpoint !== undefined) {
        endpointRows.push({
          boneId: bone.id,
          origin: formatPoint(endpoint.origin.x, endpoint.origin.y),
          tip: formatPoint(endpoint.tip.x, endpoint.tip.y)
        });
      }
    }
  }
  return {
    projectName: document.project.name,
    schemaVersion: document.schema_version,
    characterCount: document.characters.length,
    sceneCount: document.scenes.length,
    clipCount: document.clips.length,
    boneCount: character.rig.bones.length,
    attachmentCount: character.attachments.length,
    projectIssues,
    rigIssues,
    endpointRows
  };
}

export function DevFixturesPage() {
  const report = useMemo(buildReport, []);
  const issueCount = report.projectIssues.length + report.rigIssues.length;

  return (
    <section aria-label="Fixture inspection" className="page-section">
      <Title3 as="h2">Canonical biped fixture</Title3>
      <Body1 className="muted-text">
        {report.projectName} — schema {report.schemaVersion}, validated in the browser with the
        shared Zod schemas and the TypeScript math kernel.
      </Body1>

      <dl aria-label="Validated counts">
        <div>
          <dt>
            <Text weight="semibold">Characters</Text>
          </dt>
          <dd>{report.characterCount}</dd>
        </div>
        <div>
          <dt>
            <Text weight="semibold">Scenes</Text>
          </dt>
          <dd>{report.sceneCount}</dd>
        </div>
        <div>
          <dt>
            <Text weight="semibold">Clips</Text>
          </dt>
          <dd>{report.clipCount}</dd>
        </div>
        <div>
          <dt>
            <Text weight="semibold">Bones</Text>
          </dt>
          <dd>{report.boneCount}</dd>
        </div>
        <div>
          <dt>
            <Text weight="semibold">Attachments</Text>
          </dt>
          <dd>{report.attachmentCount}</dd>
        </div>
        <div>
          <dt>
            <Text weight="semibold">Validation issues</Text>
          </dt>
          <dd>
            <Badge appearance="tint" color={issueCount === 0 ? "success" : "danger"}>
              {issueCount === 0 ? "0 issues" : `${issueCount} issues`}
            </Badge>
          </dd>
        </div>
      </dl>

      {issueCount > 0 ? (
        <ul aria-label="Validation issues">
          {[...report.projectIssues, ...report.rigIssues].map((issue) => (
            <li key={`${issue.code}:${issue.path}`}>
              <Text>
                {issue.code} at {issue.path}: {issue.message}
              </Text>
            </li>
          ))}
        </ul>
      ) : null}

      <Table aria-label="Computed world endpoints" size="small">
        <TableHeader>
          <TableRow>
            <TableHeaderCell>Bone</TableHeaderCell>
            <TableHeaderCell>World origin</TableHeaderCell>
            <TableHeaderCell>World tip</TableHeaderCell>
          </TableRow>
        </TableHeader>
        <TableBody>
          {report.endpointRows.map((row) => (
            <TableRow key={row.boneId}>
              <TableCell>{row.boneId}</TableCell>
              <TableCell>{row.origin}</TableCell>
              <TableCell>{row.tip}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </section>
  );
}
