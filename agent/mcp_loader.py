from agents.mcp import MCPServer, MCPServerStdio, MCPServerStreamableHttp

from core.config import AppConfig


def load_mcp_list(config: AppConfig) -> list[MCPServer]:
    servers = []
    for name, cfg in config.mcp_servers.items():
        transport = cfg.transport
        if transport == 'stdio':
            servers.append(MCPServerStdio(
                name=name,
                params={
                    'command': cfg.command,
                    'args': cfg.args,
                    'env': cfg.env,
                    'cwd': cfg.cwd,
                },
                cache_tools_list=cfg.cache_tools_list,
                tool_filter=cfg.tool_filter,
                require_approval=cfg.require_approval,
                client_session_timeout_seconds=None,
            ))
        elif transport == 'streamable_http':
            servers.append(MCPServerStreamableHttp(
                name=name,
                params={
                    'url': cfg.url,
                    'headers': cfg.headers,
                },
                cache_tools_list=cfg.cache_tools_list,
                tool_filter=cfg.tool_filter,
                require_approval=cfg.require_approval,
                client_session_timeout_seconds=None,
            ))
    return servers
