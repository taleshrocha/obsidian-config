#!/usr/bin/env node

/**
 * Obsidian Work Vault MCP Server
 *
 * Lightweight Model Context Protocol (MCP) server for Claude Code and Gemini CLI / Antigravity.
 * Exposes native tools over stdio to search, read, list, analyze links and open notes in GUI.
 */

import fs from "node:fs";
import path from "node:path";
import readline from "node:readline";
import { execFile, execSync, execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

function resolveVaultRoot() {
    if (process.env.OBSIDIAN_VAULT_PATH) return process.env.OBSIDIAN_VAULT_PATH;
    const xdg = process.env.XDG_CONFIG_HOME || path.join(process.env.HOME || "", ".config");
    try {
        const cfg = JSON.parse(fs.readFileSync(path.join(xdg, "obsidian-config", "config.json"), "utf8"));
        if (cfg.vault) return cfg.vault;
    } catch (_) {}
    throw new Error("Vault não configurado: defina OBSIDIAN_VAULT_PATH ou rode install.sh --vault <caminho>.");
}

const VAULT_ROOT = path.resolve(resolveVaultRoot());

function loadVaultConfig() {
    const defaults = {
        vault_name: path.basename(VAULT_ROOT),
        change_id_author: false,
        journal: { dir: "13 - Meetings", per_author: false, type: "meeting" },
        mcp_name: "obsidian-vault",
    };
    try {
        const cfg = JSON.parse(fs.readFileSync(path.join(VAULT_ROOT, ".vault", "config.json"), "utf8"));
        return { ...defaults, ...cfg, journal: { ...defaults.journal, ...(cfg.journal || {}) } };
    } catch (_) {
        return defaults;
    }
}
const VAULT_CFG = loadVaultConfig();

function slugify(s) {
    return s.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
}

function resolveAuthor() {
    if (process.env.VAULT_AUTHOR) return slugify(process.env.VAULT_AUTHOR);
    try {
        const name = execFileSync("git", ["-C", VAULT_ROOT, "config", "user.name"], { encoding: "utf8", timeout: 3000 }).trim();
        if (name) return slugify(name);
    } catch (_) {}
    return "unknown";
}
const AUTHOR = resolveAuthor();

// Layout do vault (espelha lib/vaultcfg.py): subpastas AAAA/MM e uma nota de pessoa por autor.
const LAYOUT = { date_folders: [], people_dir: "", people_aliases: {}, ...(VAULT_CFG.layout || {}) };

function dateSub(folder, dateStr) {
    return LAYOUT.date_folders.includes(folder) ? path.join(dateStr.slice(0, 4), dateStr.slice(5, 7)) : "";
}

function frontmatterField(text, key) {
    const m = text.match(/^---\r?\n([\s\S]*?)\r?\n---/);
    const f = m && m[1].match(new RegExp(`^${key}:[ \\t]*(.*)$`, "m"));
    return f ? f[1].trim().replace(/^['"]|['"]$/g, "") : "";
}

function frontmatterList(text, key) {
    const m = text.match(/^---\r?\n([\s\S]*?)\r?\n---/);
    if (!m) return [];
    const km = m[1].match(new RegExp(`^${key}:[ \\t]*(.*)$`, "m"));
    if (!km) return [];
    if (km[1].trim()) return km[1].trim().replace(/^\[|\]$/g, "").split(",").map(v => v.trim().replace(/^['"]|['"]$/g, "")).filter(Boolean);
    const rest = m[1].slice(km.index + km[0].length).match(/^(?:\n[ \t]+-[^\n]*)*/)[0];
    return rest.split("\n").filter(l => l.trim()).map(l => l.split("-").slice(1).join("-").trim().replace(/^['"]|['"]$/g, ""));
}

// Nota de pessoa do autor atual em people_dir (criada se faltar). Devolve o nome da nota, ou "" se desligado.
function ensurePerson() {
    if (!LAYOUT.people_dir) return "";
    const dir = path.join(VAULT_ROOT, LAYOUT.people_dir);
    fs.mkdirSync(dir, { recursive: true });
    const alias = LAYOUT.people_aliases[AUTHOR];
    if (alias && fs.existsSync(path.join(dir, `${alias}.md`))) return alias;
    for (const f of fs.readdirSync(dir).filter(n => n.endsWith(".md")).sort()) {
        const text = fs.readFileSync(path.join(dir, f), "utf8");
        if (frontmatterField(text, "type") !== "person") continue;
        const ids = [frontmatterField(text, "author"), ...frontmatterList(text, "git_authors")];
        if (ids.some(i => i && slugify(i) === AUTHOR)) return f.slice(0, -3);
    }
    // Nome no git difere do nome da nota: "Maria Souza" = "mariasouza" (ignora espaços e hífens).
    const norm = t => slugify(t).replace(/-/g, "");
    for (const f of fs.readdirSync(dir).filter(n => n.endsWith(".md")).sort()) {
        if (frontmatterField(fs.readFileSync(path.join(dir, f), "utf8"), "type") === "person" && norm(f.slice(0, -3)) === norm(AUTHOR)) return f.slice(0, -3);
    }
    let display = process.env.VAULT_AUTHOR || "";
    if (!display) {
        try { display = execFileSync("git", ["-C", VAULT_ROOT, "config", "user.name"], { encoding: "utf8", timeout: 3000 }).trim(); } catch (_) {}
    }
    const name = (display || AUTHOR).replace(/[/\\?%*:|"<>]/g, "-").trim();
    const note = path.join(dir, `${name}.md`);
    if (!fs.existsSync(note)) {
        const org = (VAULT_CFG.organizations || [])[0] || "";
        fs.writeFileSync(note, `---\ntype: person\nname: ${name}\norganization: ${org}\nauthor: ${AUTHOR}\nrole: \nstatus: active\nlast_verified: ${new Date().toISOString().slice(0, 10)}\n---\n\n# ${name}\n\n## Visão Geral\n\nResumo da atuação e das responsabilidades da pessoa no time.\n\n## Documentos Relacionados\n\nChanges, diários e notas que citam esta pessoa aparecem no painel de backlinks do Obsidian.\n`, "utf8");
    }
    return name;
}

// Vault de time (shared_repo): antes de cada ferramenta, traz o que os colegas publicaram.
// fetch + merge --ff-only, no máximo a cada `auto_pull_ttl_seconds`. Nunca faz rebase nem
// mexe em commit local: se houver divergência ou falha de rede, avisa na saída da ferramenta.
// Ordem do token: variável de ambiente (token_env), arquivo (token_file), cofre de credenciais do git.
function resolveToken(rule, remoteUrl) {
    const envVal = rule.token_env && (process.env[rule.token_env] || "").trim();
    if (envVal) return envVal;
    if (rule.token_file) {
        const file = rule.token_file.replace(/^~(?=$|[\\/])/, process.env.HOME || process.env.USERPROFILE || "");
        try {
            const tok = fs.readFileSync(file, "utf8").trim();
            if (tok) return tok;
        } catch (_) {}
    }
    try {
        const u = new URL(remoteUrl.trim());
        if (!/^https?:$/.test(u.protocol)) return "";
        const out = execFileSync("git", ["credential", "fill"], {
            input: `protocol=${u.protocol.slice(0, -1)}\nhost=${u.host}\nusername=${rule.user || "oauth2"}\n\n`,
            encoding: "utf8", timeout: 15000, stdio: ["pipe", "pipe", "ignore"],
            env: { ...process.env, GIT_TERMINAL_PROMPT: "0", GCM_INTERACTIVE: "never" },
        });
        const line = out.split("\n").find(l => l.startsWith("password="));
        return line ? line.slice("password=".length).trim() : "";
    } catch (_) {
        return "";
    }
}

function httpsAuthArgs(remoteUrl) {
    // Regras git_https_auth do próprio vault ou do vault pessoal que o monta (pastas acima).
    const rules = [...(VAULT_CFG.git_https_auth || [])];
    for (let dir = path.dirname(VAULT_ROOT); dir !== path.dirname(dir); dir = path.dirname(dir)) {
        try {
            rules.push(...(JSON.parse(fs.readFileSync(path.join(dir, ".vault", "config.json"), "utf8")).git_https_auth || []));
            break;
        } catch (_) {}
    }
    for (const rule of rules) {
        if (!rule.host_contains || !remoteUrl.includes(rule.host_contains)) continue;
        const token = resolveToken(rule, remoteUrl);
        if (!token) continue;
        const basic = Buffer.from(`${rule.user || "oauth2"}:${token}`).toString("base64");
        return ["-c", `http.extraheader=Authorization: Basic ${basic}`];
    }
    return [];
}

const AUTO_PULL = VAULT_CFG.auto_pull ?? Boolean(VAULT_CFG.shared_repo);
const AUTO_PULL_TTL_MS = (Number(process.env.VAULT_AUTO_PULL_TTL_SECONDS) || VAULT_CFG.auto_pull_ttl_seconds || 300) * 1000;
let lastPullAt = 0;
let pullWarning = "";

function autoPull() {
    if (!AUTO_PULL || !fs.existsSync(path.join(VAULT_ROOT, ".git"))) return "";
    if (Date.now() - lastPullAt < AUTO_PULL_TTL_MS) return pullWarning;
    lastPullAt = Date.now();
    pullWarning = tryPull();
    return pullWarning;
}

function tryPull() {
    const git = (args, timeout = 5000) =>
        execFileSync("git", ["-C", VAULT_ROOT, ...args], { encoding: "utf8", timeout, stdio: ["ignore", "pipe", "pipe"] }).trim();
    const remote = (VAULT_CFG.git && VAULT_CFG.git.remote) || "origin";
    const branch = (VAULT_CFG.git && VAULT_CFG.git.branch) || "main";
    try {
        const url = git(["remote", "get-url", remote]);
        git([...httpsAuthArgs(url), "fetch", "--quiet", remote, branch], 20000);
        const [ahead, behind] = git(["rev-list", "--left-right", "--count", `HEAD...${remote}/${branch}`]).split(/\s+/).map(Number);
        if (!behind) return "";
        if (ahead) return `[aviso] Vault do time divergiu de ${remote}/${branch} (${ahead} local, ${behind} remoto). Rode \`git pull --rebase\` antes de confiar no resultado.\n\n`;
        git(["merge", "--ff-only", "--quiet", `${remote}/${branch}`], 10000);
        return "";
    } catch (err) {
        // Só stderr: err.message repete a linha de comando, que leva o header com o token.
        const msg = String(err.stderr || "").split("\n").find(l => l.trim()) || (err.code === "ETIMEDOUT" ? "timeout" : "erro do git");
        return `[aviso] Não consegui atualizar o vault do time (${msg.trim()}). O resultado pode estar desatualizado.\n\n`;
    }
}

function pythonCmd() {
    // python3 (Linux/macOS), python ou py -3 (Windows)
    for (const cand of [["python3"], ["python"], ["py", "-3"]]) {
        try {
            execFileSync(cand[0], [...cand.slice(1), "--version"], { stdio: "ignore", timeout: 3000 });
            return cand;
        } catch (_) {}
    }
    return ["python3"];
}

function parseFrontmatter(content) {
    if (!content.startsWith("---\n")) return { properties: {}, body: content };
    const endIndex = content.indexOf("\n---\n", 4);
    if (endIndex === -1) return { properties: {}, body: content };
    const yamlBlock = content.slice(4, endIndex);
    const body = content.slice(endIndex + 5);
    const properties = {};
    for (const line of yamlBlock.split("\n")) {
        const match = line.match(/^([a-zA-Z0-9_-]+):\s*(.*)$/);
        if (match) {
            let val = match[2].trim();
            if (val.startsWith('"') && val.endsWith('"')) val = val.slice(1, -1);
            if (val.startsWith("'") && val.endsWith("'")) val = val.slice(1, -1);
            properties[match[1]] = val;
        }
    }
    return { properties, body };
}

function getAllMarkdownFiles(dir = VAULT_ROOT, fileList = []) {
    const entries = fs.readdirSync(dir, { withFileTypes: true });
    for (const entry of entries) {
        if (entry.name.startsWith(".") || entry.name === "node_modules") continue;
        const fullPath = path.join(dir, entry.name);
        if (entry.isDirectory()) {
            getAllMarkdownFiles(fullPath, fileList);
        } else if (entry.isFile() && entry.name.endsWith(".md")) {
            fileList.push(fullPath);
        }
    }
    return fileList;
}

function resolveNotePath(noteRef) {
    let target = noteRef.trim();
    if (target.endsWith(".md")) target = target.slice(0, -3);
    const directMd = path.join(VAULT_ROOT, target + ".md");
    if (fs.existsSync(directMd)) return directMd;
    const direct = path.join(VAULT_ROOT, target);
    if (fs.existsSync(direct) && fs.statSync(direct).isFile()) return direct;

    const baseName = path.basename(target).toLowerCase();
    const allFiles = getAllMarkdownFiles();
    for (const f of allFiles) {
        const fBase = path.basename(f, ".md").toLowerCase();
        if (fBase === baseName) return f;
    }
    return null;
}

// Tool definitions
const TOOLS = [
    {
        name: "search_vault",
        description: "Search notes across the Obsidian Work Vault by keyword or phrase. Returns matching note names, relative paths and relevant snippet lines.",
        inputSchema: {
            type: "object",
            properties: {
                query: { type: "string", description: "Keyword or phrase to search for." },
                folder: { type: "string", description: "Optional folder prefix to narrow search (e.g. '04 - Servers', '10 - Procedures')." },
                limit: { type: "integer", description: "Maximum number of results to return (default: 10)." }
            },
            required: ["query"]
        }
    },
    {
        name: "read_note",
        description: "Read the full markdown content and YAML properties of a specific note in the Obsidian Work Vault.",
        inputSchema: {
            type: "object",
            properties: {
                path_or_title: { type: "string", description: "Relative path or note title (e.g. 'app-prod-01' or '04 - Servers/Org/app-prod-01.md')." }
            },
            required: ["path_or_title"]
        }
    },
    {
        name: "read_metadata",
        description: "Read ONLY the YAML frontmatter properties of a specific note, consuming minimal tokens (~20-50 tokens) instead of reading the full document body.",
        inputSchema: {
            type: "object",
            properties: {
                path_or_title: { type: "string", description: "Relative path or note title (e.g. 'app-prod-01' or '04 - Servers/Org/app-prod-01.md')." }
            },
            required: ["path_or_title"]
        }
    },
    {
        name: "read_section",
        description: "Read ONLY a specific markdown section (under a heading) of a note, saving up to 95% of tokens compared to reading the full file.",
        inputSchema: {
            type: "object",
            properties: {
                path_or_title: { type: "string", description: "Relative path or note title (e.g. 'app-prod-01' or '04 - Servers/Org/app-prod-01.md')." },
                heading: { type: "string", description: "Heading text of the section to retrieve (e.g. 'Acesso e Conectividade' or 'Serviços Hospedados')." }
            },
            required: ["path_or_title", "heading"]
        }
    },
    {
        name: "get_outline",
        description: "Retrieve the hierarchical table of contents / headings outline (#, ##, ###) of a note without reading the body text.",
        inputSchema: {
            type: "object",
            properties: {
                path_or_title: { type: "string", description: "Relative path or note title (e.g. 'app-prod-01' or '04 - Servers/Org/app-prod-01.md')." }
            },
            required: ["path_or_title"]
        }
    },
    {
        name: "list_notes",
        description: "List notes in the vault filtered by type (server, project, change, procedure, repository, application) or organization (as definidas em 01 - Organizations).",
        inputSchema: {
            type: "object",
            properties: {
                type: { type: "string", description: "Filter by note frontmatter type (e.g. 'server', 'project', 'change', 'procedure')." },
                organization: { type: "string", description: "Filter by organization (nome da nota em 01 - Organizations ou 'Cross-Organization')." },
                folder: { type: "string", description: "Filter by vault folder prefix (e.g. '08 - Changes/2026')." },
                limit: { type: "integer", description: "Max results (default: 25)." }
            }
        }
    },
    {
        name: "get_backlinks",
        description: "Find all notes in the vault that link to a specific note via [[wikilinks]].",
        inputSchema: {
            type: "object",
            properties: {
                note_name: { type: "string", description: "Name of the note to find incoming links for." }
            },
            required: ["note_name"]
        }
    },
    {
        name: "open_in_gui",
        description: "Open a note in the active Obsidian desktop GUI window using obsidian-cli.",
        inputSchema: {
            type: "object",
            properties: {
                path: { type: "string", description: "Relative path or note name to open in the Obsidian desktop application." }
            },
            required: ["path"]
        }
    },
    {
        name: "validate_vault",
        description: "Execute the official vault integrity validator (bin/vault-validate deste repositório) and return structure, link and secret check status.",
        inputSchema: {
            type: "object",
            properties: {}
        }
    },
    {
        name: "create_change_record",
        description: "Create a formal, sequentially numbered Change record (CHG-YYYY-MM-DD-NNN) in 08 - Changes/YYYY/ following vault standards, and optionally open it in the Obsidian GUI.",
        inputSchema: {
            type: "object",
            properties: {
                title: { type: "string", description: "Short descriptive title of the change (e.g. 'Deploy do Backend v2')." },
                server: { type: "string", description: "Affected server (e.g. 'app-prod-01' or 'workstation-01')." },
                service: { type: "string", description: "Affected service (e.g. 'PostgreSQL', 'Keycloak', 'Docker Compose')." },
                project: { type: "string", description: "Affected project (e.g. 'Org - Projeto' or 'Cross-Organization')." },
                risk: { type: "string", enum: ["low", "medium", "high"], description: "Risk evaluation." },
                description: { type: "string", description: "Motivation and description of changes made." },
                status: { type: "string", enum: ["proposed", "in-progress", "completed"], description: "Change status (default: 'completed')." },
                open_gui: { type: "boolean", description: "Whether to immediately open the created note in Obsidian GUI." }
            },
            required: ["title", "server", "service", "project", "risk", "description"]
        }
    },
    {
        name: "append_daily_log",
        description: "Append a timestamped entry or meeting log into today's log in 13 - Meetings/YYYY-MM-DD.md.",
        inputSchema: {
            type: "object",
            properties: {
                content: { type: "string", description: "Markdown text describing the activity or notes to append." },
                heading: { type: "string", description: "Section heading (default: 'Atividade do Agente IA')." }
            },
            required: ["content"]
        }
    },
    {
        name: "get_architecture_topology",
        description: "Retrieve a consolidated overview of servers, services, applications and architecture documents for an organization.",
        inputSchema: {
            type: "object",
            properties: {
                organization: { type: "string", description: "Organization name (nota em 01 - Organizations)." }
            },
            required: ["organization"]
        }
    }
];

function handleSearchVault({ query, folder, limit = 10 }) {
    if (!query) throw new Error("query is required");
    const qLower = query.toLowerCase();
    const files = getAllMarkdownFiles();
    const results = [];

    for (const f of files) {
        const rel = path.relative(VAULT_ROOT, f);
        if (folder && !rel.toLowerCase().startsWith(folder.toLowerCase())) continue;
        const content = fs.readFileSync(f, "utf8");
        if (content.toLowerCase().includes(qLower) || rel.toLowerCase().includes(qLower)) {
            const lines = content.split("\n");
            const snippets = [];
            for (let i = 0; i < lines.length && snippets.length < 3; i++) {
                if (lines[i].toLowerCase().includes(qLower)) {
                    snippets.push(`L${i + 1}: ${lines[i].trim()}`);
                }
            }
            results.push({
                file: rel,
                snippets: snippets.slice(0, 3)
            });
            if (results.length >= limit) break;
        }
    }

    if (results.length === 0) return `Nenhum resultado encontrado para '${query}'.`;
    return results
        .map(r => `### [[${r.file}]]\n${r.snippets.join("\n")}`)
        .join("\n\n");
}

function handleReadNote({ path_or_title }) {
    const fullPath = resolveNotePath(path_or_title);
    if (!fullPath) throw new Error(`Nota '${path_or_title}' não encontrada no vault.`);
    const content = fs.readFileSync(fullPath, "utf8");
    const rel = path.relative(VAULT_ROOT, fullPath);
    const { properties } = parseFrontmatter(content);
    return `# [[${rel}]]\n\nProperties:\n${JSON.stringify(properties, null, 2)}\n\n---\n\n${content}`;
}

function handleReadMetadata({ path_or_title }) {
    const fullPath = resolveNotePath(path_or_title);
    if (!fullPath) throw new Error(`Nota '${path_or_title}' não encontrada no vault.`);
    const content = fs.readFileSync(fullPath, "utf8");
    const rel = path.relative(VAULT_ROOT, fullPath);
    const { properties } = parseFrontmatter(content);
    return `# [[${rel}]] (YAML Frontmatter Only)\n\n${JSON.stringify(properties, null, 2)}`;
}

function handleReadSection({ path_or_title, heading }) {
    const fullPath = resolveNotePath(path_or_title);
    if (!fullPath) throw new Error(`Nota '${path_or_title}' não encontrada no vault.`);
    const content = fs.readFileSync(fullPath, "utf8");
    const rel = path.relative(VAULT_ROOT, fullPath);
    const lines = content.split("\n");
    const targetHeading = heading.trim().toLowerCase();
    let found = false;
    let level = 0;
    const sectionLines = [];

    for (const line of lines) {
        const m = line.match(/^(#{1,6})\s+(.*)/);
        if (m) {
            const hLevel = m[1].length;
            const hText = m[2].trim().toLowerCase();
            if (!found) {
                if (hText.includes(targetHeading)) {
                    found = true;
                    level = hLevel;
                    sectionLines.push(line);
                }
            } else {
                if (hLevel <= level) {
                    break;
                } else {
                    sectionLines.push(line);
                }
            }
        } else if (found) {
            sectionLines.push(line);
        }
    }

    if (!found) throw new Error(`Seção '${heading}' não encontrada em [[${rel}]].`);
    return `# [[${rel}]] → Seção: "${heading}"\n\n${sectionLines.join("\n").trim()}`;
}

function handleGetOutline({ path_or_title }) {
    const fullPath = resolveNotePath(path_or_title);
    if (!fullPath) throw new Error(`Nota '${path_or_title}' não encontrada no vault.`);
    const content = fs.readFileSync(fullPath, "utf8");
    const rel = path.relative(VAULT_ROOT, fullPath);
    const lines = content.split("\n");
    const headings = [];
    for (const line of lines) {
        const m = line.match(/^(#{1,6})\s+(.*)/);
        if (m) {
            headings.push(`${"  ".repeat(m[1].length - 1)}- ${m[2].trim()} (${m[1]})`);
        }
    }
    if (headings.length === 0) return `# [[${rel}]]\n(Sem cabeçalhos estruturados)`;
    return `# [[${rel}]] Outline:\n${headings.join("\n")}`;
}

function handleListNotes({ type, organization, folder, limit = 25 }) {
    const files = getAllMarkdownFiles();
    const matched = [];

    for (const f of files) {
        const rel = path.relative(VAULT_ROOT, f);
        if (folder && !rel.toLowerCase().startsWith(folder.toLowerCase())) continue;
        const content = fs.readFileSync(f, "utf8");
        const { properties } = parseFrontmatter(content);
        if (type && properties.type !== type) continue;
        if (organization && properties.organization !== organization) continue;
        matched.push({
            file: rel,
            type: properties.type || "unknown",
            organization: properties.organization || "-",
            status: properties.status || "-"
        });
        if (matched.length >= limit) break;
    }

    if (matched.length === 0) return "Nenhuma nota encontrada com os filtros especificados.";
    const header = "| Nota | Tipo | Organização | Status |\n|---|---|---|---|";
    const rows = matched.map(m => `| [[${m.file}]] | \`${m.type}\` | ${m.organization} | ${m.status} |`);
    return `${header}\n${rows.join("\n")}`;
}

function handleGetBacklinks({ note_name }) {
    const cleanName = note_name.replace(/\.md$/, "").trim();
    const files = getAllMarkdownFiles();
    const backlinks = [];
    const linkPattern = new RegExp(`\\[\\[([^\\]|#]+)(?:[|#][^\\]]*)?\\]\\]`, "g");

    for (const f of files) {
        const rel = path.relative(VAULT_ROOT, f);
        const content = fs.readFileSync(f, "utf8");
        let match;
        while ((match = linkPattern.exec(content)) !== null) {
            const target = match[1].trim();
            const targetBase = path.basename(target, ".md");
            if (target === cleanName || targetBase === cleanName || target.endsWith("/" + cleanName)) {
                backlinks.push(rel);
                break;
            }
        }
    }

    if (backlinks.length === 0) return `Nenhum backlink encontrado apontando para '${cleanName}'.`;
    return `Backlinks para '${cleanName}':\n` + backlinks.map(b => `- [[${b}]]`).join("\n");
}

function handleOpenInGui({ path: targetPath }) {
    try {
        const out = execSync(`obsidian-cli open file="${targetPath}"`, {
            encoding: "utf8",
            timeout: 5000
        });
        return `Sucesso: ${out.trim()}`;
    } catch (err) {
        return `Erro ao abrir no Obsidian GUI via obsidian-cli: ${err.message}`;
    }
}

function handleValidateVault() {
    try {
        const out = execFileSync(pythonCmd()[0], [...pythonCmd().slice(1), "-X", "utf8", path.join(REPO_ROOT, "bin", "vault-validate"), VAULT_ROOT], {
            encoding: "utf8",
            timeout: 10000
        });
        return out.trim();
    } catch (err) {
        return `Validação falhou ou com avisos:\n${err.stdout || err.message}`;
    }
}

function handleCreateChangeRecord({ title, server, service, project, risk = "low", description, status = "completed", open_gui = false }) {
    const now = new Date();
    const yyyy = now.getFullYear();
    const mm = String(now.getMonth() + 1).padStart(2, "0");
    const dd = String(now.getDate()).padStart(2, "0");
    const dateStr = `${yyyy}-${mm}-${dd}`;
    const yearDir = path.join(VAULT_ROOT, "08 - Changes", dateSub("08 - Changes", dateStr) || String(yyyy));
    fs.mkdirSync(yearDir, { recursive: true });
    const whoName = ensurePerson();

    const files = fs.readdirSync(yearDir);
    let maxSeq = 0;
    const prefix = `CHG-${dateStr}-` + (VAULT_CFG.change_id_author ? `${AUTHOR}-` : "");
    for (const f of files) {
        if (f.startsWith(prefix)) {
            const numPart = f.slice(prefix.length, prefix.length + 3);
            const num = parseInt(numPart, 10);
            if (!isNaN(num) && num > maxSeq) maxSeq = num;
        }
    }
    const nextSeq = String(maxSeq + 1).padStart(3, "0");
    const changeId = `${prefix}${nextSeq}`;
    const sanitizedTitle = title.replace(/[/\\?%*:|"<>]/g, "-").trim();
    const fileName = `${changeId} - ${sanitizedTitle}.md`;
    const fullPath = path.join(yearDir, fileName);
    const relPath = path.relative(VAULT_ROOT, fullPath);

    const srvLink = server.startsWith("[[") ? server : `[[${server}]]`;
    const svcLink = service.startsWith("[[") ? service : `[[${service}]]`;
    const prjLink = project.startsWith("[[") ? project : `[[${project}]]`;

    const content = `---
type: change
id: ${changeId}
date: ${dateStr}
server: ${server.replace(/^\[\[|\]\]$/g, "")}
service: ${service.replace(/^\[\[|\]\]$/g, "")}
project: ${project.replace(/^\[\[|\]\]$/g, "")}
${VAULT_CFG.change_id_author ? `author: ${AUTHOR}\n` : ""}agent: AI Agent
risk: ${risk}
status: ${status}
environment: production
---

# ${changeId} - ${sanitizedTitle}

## Metadados

- **ID:** \`${changeId}\`
- **Data:** \`${dateStr}\`
${whoName ? `- **Autor:** [[${whoName}]]\n` : ""}- **Projeto:** ${prjLink}
- **Servidor:** ${srvLink}
- **Serviço:** ${svcLink}
- **Ambiente:** \`production\`
- **Risco:** \`${risk}\`
- **Status:** \`${status}\`

---

## 1. Motivação e Descrição

${description}

---

## 2. Alterações Realizadas

- [ ] Detalhes das alterações técnicas executadas

---

## 3. Validação

- [ ] Testes e verificações efetuadas
`;

    fs.writeFileSync(fullPath, content, "utf8");

    let guiMsg = "";
    if (open_gui) {
        try {
            execSync(`obsidian-cli open file="${relPath}"`, { timeout: 3000 });
            guiMsg = " e aberta no Obsidian GUI";
        } catch (_) {}
    }

    return `Change criada com sucesso${guiMsg}:\n- Arquivo: [[${relPath}]]\n- ID: \`${changeId}\`\n- Data: \`${dateStr}\``;
}

function handleAppendDailyLog({ content, heading = "Atividade do Agente IA" }) {
    const now = new Date();
    const yyyy = now.getFullYear();
    const mm = String(now.getMonth() + 1).padStart(2, "0");
    const dd = String(now.getDate()).padStart(2, "0");
    const dateStr = `${yyyy}-${mm}-${dd}`;
    const hh = String(now.getHours()).padStart(2, "0");
    const min = String(now.getMinutes()).padStart(2, "0");
    const timeStr = `${hh}:${min}`;

    const journalBase = VAULT_CFG.journal.per_author
        ? path.join(VAULT_ROOT, VAULT_CFG.journal.dir, AUTHOR)
        : path.join(VAULT_ROOT, VAULT_CFG.journal.dir);
    const meetingsDir = path.join(journalBase, dateSub(VAULT_CFG.journal.dir, dateStr));
    fs.mkdirSync(meetingsDir, { recursive: true });
    const logFile = path.join(meetingsDir, `${dateStr}.md`);
    const relPath = path.relative(VAULT_ROOT, logFile);

    let prefix = "";
    if (!fs.existsSync(logFile)) {
        const whoName = VAULT_CFG.journal.per_author ? ensurePerson() : "";
        prefix = `---
type: ${VAULT_CFG.journal.type || "meeting"}
title: Daily Log ${dateStr}
date: ${dateStr}
${VAULT_CFG.journal.per_author ? `author: ${AUTHOR}\n` : ""}status: completed
---

# Daily Log · ${dateStr}
${whoName ? `\nAutor: [[${whoName}]]\n` : ""}
`;
    }

    const entry = `${prefix}\n### [${timeStr}] ${heading}\n\n${content}\n`;
    fs.appendFileSync(logFile, entry, "utf8");

    return `Entrada adicionada com sucesso em [[${relPath}]]:\n[${timeStr}] ${heading}`;
}

function handleGetArchitectureTopology({ organization }) {
    const files = getAllMarkdownFiles();
    const servers = [];
    const services = [];
    const applications = [];
    const architectures = [];

    for (const f of files) {
        const rel = path.relative(VAULT_ROOT, f);
        const content = fs.readFileSync(f, "utf8");
        const { properties } = parseFrontmatter(content);
        if (organization && properties.organization !== organization && properties.organization !== "Cross-Organization") continue;

        if (rel.startsWith("04 - Servers/")) {
            servers.push(`- **[[${rel}|${path.basename(rel, ".md")}]]**: IP \`${properties.ip || properties.hostname || "-"}\` (${properties.environment || "-"})`);
        } else if (rel.startsWith("05 - Services/")) {
            services.push(`- **[[${rel}|${path.basename(rel, ".md")}]]**: Porta \`${properties.port || "-"}\` em ${properties.server || "-"}`);
        } else if (rel.startsWith("06 - Applications/")) {
            applications.push(`- **[[${rel}|${path.basename(rel, ".md")}]]**: ${properties.type || "app"} (${properties.environment || "-"})`);
        } else if (rel.startsWith("11 - Architecture/")) {
            architectures.push(`- [[${rel}|${path.basename(rel, ".md")}]]`);
        }
    }

    return `# Topologia de Arquitetura · ${organization}

## 🖥️ Servidores
${servers.length > 0 ? servers.join("\n") : "_Nenhum servidor mapeado._"}

## ⚙️ Serviços e Daemons
${services.length > 0 ? services.join("\n") : "_Nenhum serviço mapeado._"}

## 📱 Aplicações
${applications.length > 0 ? applications.join("\n") : "_Nenhuma aplicação mapeada._"}

## 📐 Documentos de Arquitetura
${architectures.length > 0 ? architectures.join("\n") : "_Nenhum documento de arquitetura._"}
`;
}

function handleSemanticSearchVault({ query, limit = 5 }) {
    if (!query) throw new Error("query is required");
    // Fallback leve para busca textual para eliminar consumo excessivo de CPU do ONNX/FastEmbed
    return `> [!NOTE]\n> A busca vetorial neural foi desativada em prol do desempenho da máquina. Executando busca textual rápida:\n\n` + handleSearchVault({ query, limit });
}

// JSON-RPC dispatcher
const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout,
    terminal: false
});

function sendResponse(response) {
    process.stdout.write(JSON.stringify(response) + "\n");
}

rl.on("line", line => {
    if (!line.trim()) return;
    let message;
    try {
        message = JSON.parse(line);
    } catch (err) {
        sendResponse({
            jsonrpc: "2.0",
            id: null,
            error: { code: -32700, message: "Parse error" }
        });
        return;
    }

    const { id, method, params } = message;

    // Handle notifications (no id)
    if (id === undefined || id === null) {
        return;
    }

    if (method === "initialize") {
        sendResponse({
            jsonrpc: "2.0",
            id,
            result: {
                protocolVersion: "2024-11-05",
                capabilities: {
                    tools: {}
                },
                serverInfo: {
                    name: VAULT_CFG.mcp_name || "obsidian-vault",
                    version: "1.0.0"
                }
            }
        });
        return;
    }

    if (method === "ping") {
        sendResponse({ jsonrpc: "2.0", id, result: {} });
        return;
    }

    if (method === "tools/list") {
        sendResponse({
            jsonrpc: "2.0",
            id,
            result: {
                tools: TOOLS
            }
        });
        return;
    }

    if (method === "tools/call") {
        const toolName = params?.name;
        const toolArgs = params?.arguments || {};
        try {
            const syncWarning = autoPull();
            let output;
            switch (toolName) {
                case "search_vault":
                    output = handleSearchVault(toolArgs);
                    break;
                case "read_note":
                    output = handleReadNote(toolArgs);
                    break;
                case "read_metadata":
                    output = handleReadMetadata(toolArgs);
                    break;
                case "read_section":
                    output = handleReadSection(toolArgs);
                    break;
                case "get_outline":
                    output = handleGetOutline(toolArgs);
                    break;
                case "list_notes":
                    output = handleListNotes(toolArgs);
                    break;
                case "get_backlinks":
                    output = handleGetBacklinks(toolArgs);
                    break;
                case "open_in_gui":
                    output = handleOpenInGui(toolArgs);
                    break;
                case "validate_vault":
                    output = handleValidateVault();
                    break;
                case "create_change_record":
                    output = handleCreateChangeRecord(toolArgs);
                    break;
                case "append_daily_log":
                    output = handleAppendDailyLog(toolArgs);
                    break;
                case "get_architecture_topology":
                    output = handleGetArchitectureTopology(toolArgs);
                    break;
                case "semantic_search_vault":
                    output = handleSemanticSearchVault(toolArgs);
                    break;
                default:
                    sendResponse({
                        jsonrpc: "2.0",
                        id,
                        error: { code: -32601, message: `Tool not found: ${toolName}` }
                    });
                    return;
            }
            sendResponse({
                jsonrpc: "2.0",
                id,
                result: {
                    content: [
                        {
                            type: "text",
                            text: syncWarning + output
                        }
                    ]
                }
            });
        } catch (err) {
            sendResponse({
                jsonrpc: "2.0",
                id,
                result: {
                    content: [
                        {
                            type: "text",
                            text: `Erro executando ${toolName}: ${err.message}`
                        }
                    ],
                    isError: true
                }
            });
        }
        return;
    }

    sendResponse({
        jsonrpc: "2.0",
        id,
        error: { code: -32601, message: `Method not found: ${method}` }
    });
});
