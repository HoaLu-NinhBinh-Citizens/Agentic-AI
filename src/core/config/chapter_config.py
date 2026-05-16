CHAPTER_VALIDATION_RULES = {
    "CLOCK_TREE": {
        "critical": False,
        "register_patterns": [r"\bRCC\b", r"\bCFGR\b", r"\bPLLCFGR\b"],
        "bitfield_patterns": [r"\bSW\b", r"\bSWS\b", r"\bPLLM\b", r"\bPLLN\b", r"\bPLLP\b"],
    },
    "RCC": {
        "critical": True,
        "register_patterns": [r"\bRCC\b", r"\bAHB1ENR\b", r"\bAPB1ENR\b", r"\bAPB2ENR\b"],
        "bitfield_patterns": [r"\bUSART\d?EN\b|\bUSART\b", r"\bGPIO[A-I]?EN\b|\bGPIO\b", r"\bDMA[12]?EN\b|\bDMA\b"],
    },
    "GPIO": {
        "critical": False,
        "register_patterns": [r"\bGPIO[A-I]\b|\bGPIOx\b", r"\bMODER\b", r"\bOTYPER\b", r"\bOSPEEDR\b", r"\bPUPDR\b"],
        "bitfield_patterns": [r"\bMODER\d+\b|\bMODER\b", r"\bPUPDR\d+\b|\bPUPDR\b", r"\bOSPEEDR\d+\b|\bOSPEEDR\b"],
    },
    "AF_MAPPING": {
        "critical": False,
        "register_patterns": [r"\bGPIO[A-I]\b|\bGPIOx\b", r"\bAFR[HL]?\b"],
        "bitfield_patterns": [r"\bAF7\b", r"\bAFR[HL]?\b"],
    },
    "USART": {
        "critical": True,
        "register_patterns": [r"\bUSART[1236]?\b|\bUSARTx\b", r"\bBRR\b", r"\bCR1\b", r"\bCR2\b", r"\bCR3\b", r"\bSR\b", r"\bDR\b"],
        "bitfield_patterns": [r"\bUE\b", r"\bTE\b", r"\bRE\b", r"\bRXNE\b", r"\bTXE\b"],
    },
    "NVIC": {
        "critical": False,
        "register_patterns": [r"\bNVIC\b", r"\bIRQn\b|\bIRQ\b", r"\bISER\b", r"\bIPR\b"],
        "bitfield_patterns": [r"\bIRQn\b|\bIRQ\b", r"\bpriority\b", r"\benable\b"],
    },
    "DMA": {
        "critical": True,
        "register_patterns": [r"\bDMA[12]\b|\bDMAx\b", r"\bSxCR\b|\bCR\b", r"\bSxNDTR\b|\bNDTR\b", r"\bSxPAR\b|\bPAR\b", r"\bSxM0AR\b|\bM0AR\b"],
        "bitfield_patterns": [r"\bCHSEL\b", r"\bDIR\b", r"\bMINC\b", r"\bTCIE\b", r"\bEN\b"],
    },
    "TIMERS": {
        "critical": False,
        "register_patterns": [r"\bTIM[1-9]\d*\b|\bTIMx\b", r"\bPSC\b", r"\bARR\b", r"\bCNT\b", r"\bSR\b"],
        "bitfield_patterns": [r"\bUIF\b", r"\bCEN\b"],
    },
}


STM32F407_REGISTER_HINTS = {
    "CLOCK_TREE": {
        "registers": ["RCC_CR", "RCC_PLLCFGR", "RCC_CFGR"],
        "bitfields": ["HSION", "HSEON", "PLLM", "PLLN", "PLLP", "SW", "SWS"],
        "notes": [
            "Clock tree setup must stabilize HSE/PLL before switching SYSCLK.",
            "Baud-rate dependent peripherals need the correct APB clock after prescaler selection.",
        ],
    },
    "RCC": {
        "registers": ["RCC_AHB1ENR", "RCC_APB1ENR", "RCC_APB2ENR"],
        "bitfields": ["GPIOAEN", "GPIOBEN", "GPIOCEN", "GPIODEN", "USART1EN", "USART2EN", "USART6EN", "DMA1EN", "DMA2EN"],
        "notes": [
            "Enable GPIO and USART clocks before writing peripheral registers.",
            "USART2/3/UART4/5 are on APB1; USART1/6 are on APB2 on STM32F407.",
        ],
    },
    "GPIO": {
        "registers": ["GPIOx_MODER", "GPIOx_OTYPER", "GPIOx_OSPEEDR", "GPIOx_PUPDR"],
        "bitfields": ["MODERy", "OTy", "OSPEEDRy", "PUPDRy"],
        "notes": [
            "UART pins need alternate-function mode plus suitable speed and pull configuration.",
        ],
    },
    "AF_MAPPING": {
        "registers": ["GPIOx_AFRL", "GPIOx_AFRH"],
        "bitfields": ["AF7", "AF8"],
        "notes": [
            "STM32F407 USART alternate-function routing usually uses AF7 for USART1/2/3 and AF8 for some UART4/5/6 mappings.",
        ],
    },
    "USART": {
        "registers": ["USART_SR", "USART_DR", "USART_BRR", "USART_CR1", "USART_CR2", "USART_CR3"],
        "bitfields": ["UE", "TE", "RE", "RXNE", "TXE", "TC", "DMAT", "DMAR", "RXNEIE"],
        "notes": [
            "BRR depends on the selected APB clock and oversampling mode.",
            "Enable UE after CR1/CR2/CR3 and BRR are configured.",
        ],
    },
    "NVIC": {
        "registers": ["NVIC_ISER", "NVIC_IPR"],
        "bitfields": ["USARTx_IRQn", "priority"],
        "notes": [
            "Enable NVIC only after pending USART interrupt sources are configured and cleared.",
        ],
    },
    "DMA": {
        "registers": ["DMA_SxCR", "DMA_SxNDTR", "DMA_SxPAR", "DMA_SxM0AR", "DMA_HISR", "DMA_HIFCR"],
        "bitfields": ["CHSEL", "DIR", "MINC", "PINC", "TCIE", "EN"],
        "notes": [
            "USART DMA mapping depends on controller, stream, and channel selection for the chosen USART instance.",
            "Disable the stream before rewriting CR/NDTR/PAR/M0AR.",
        ],
    },
    "TIMERS": {
        "registers": ["TIMx_PSC", "TIMx_ARR", "TIMx_CNT", "TIMx_SR"],
        "bitfields": ["UIF", "CEN"],
        "notes": [
            "Timer-based timeout helpers should use a clock-consistent prescaler and auto-reload configuration.",
        ],
    },
}