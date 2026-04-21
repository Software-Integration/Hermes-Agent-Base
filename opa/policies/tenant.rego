package hermes.authz

default decision := {
    "allow": false,
    "reason": "default_deny",
    "source": "opa",
    "policy_version": "2026-04-21"
}

tenant_active if {
    input.tenant.status == "active"
}

tool_allowed if {
    input.resource.tool != ""
    input.resource.tool in input.tenant.allowed_tools
}

capabilities_allowed if {
    not input.resource.capabilities
}

capabilities_allowed if {
    count(input.resource.capabilities) > 0
    every cap in input.resource.capabilities {
        cap in input.tenant.allowed_capabilities
    }
}

model_allowed if {
    input.resource.model_class != ""
    input.resource.model_class in input.tenant.allowed_model_classes
}

decision := {
    "allow": false,
    "reason": "tenant_inactive",
    "source": "opa",
    "policy_version": "2026-04-21"
} if {
    not tenant_active
}

decision := {
    "allow": false,
    "reason": "tool_not_allowed",
    "source": "opa",
    "policy_version": "2026-04-21"
} if {
    tenant_active
    input.action == "tool.execute"
    not tool_allowed
}

decision := {
    "allow": false,
    "reason": "capability_not_allowed",
    "source": "opa",
    "policy_version": "2026-04-21"
} if {
    tenant_active
    input.action == "tool.execute"
    tool_allowed
    not capabilities_allowed
}

decision := {
    "allow": false,
    "reason": "model_class_not_allowed",
    "source": "opa",
    "policy_version": "2026-04-21"
} if {
    tenant_active
    input.action == "chat.invoke"
    not model_allowed
}

decision := {
    "allow": true,
    "reason": "tool_allowed",
    "source": "opa",
    "policy_version": "2026-04-21"
} if {
    tenant_active
    input.action == "tool.execute"
    tool_allowed
    capabilities_allowed
}

decision := {
    "allow": true,
    "reason": "chat_allowed",
    "source": "opa",
    "policy_version": "2026-04-21"
} if {
    tenant_active
    input.action == "chat.invoke"
    model_allowed
}
