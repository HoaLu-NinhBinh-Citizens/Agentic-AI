from src.core.config.output_policy import OutputPolicy


def test_output_policy_uses_chip_and_capability_for_embedded_profile():
    policy = OutputPolicy()

    outputs = policy.default_allowed_outputs(
        "generate uart driver for stm32f407 with dma",
        domain_profile="stm32_embedded",
        target_chip="STM32F407",
    )

    assert outputs == [
        "AI_support/ai_generated/Inc/stm32f407_uart.h",
        "AI_support/ai_generated/Src/stm32f407_uart.c",
    ]


def test_output_policy_falls_back_to_generic_module_names():
    policy = OutputPolicy()

    outputs = policy.default_allowed_outputs(
        "implement parser",
        domain_profile="generic_document",
    )

    assert outputs == [
        "AI_support/ai_generated/Inc/module_parser.h",
        "AI_support/ai_generated/Src/module_parser.c",
    ]
