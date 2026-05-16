"""Register Access Templates - C code templates for register operations."""

from typing import Dict, List


class RegisterAccessTemplates:
    """
    C code templates for peripheral register operations.

    Provides macro-style templates that produce safe, portable
    register access code. Templates are parameterized by
    peripheral name, register name, and bitfield details.
    """

    # ─── GPIO ────────────────────────────────────────────────────────

    GPIO_INIT = """\
void gpio_init_{pin}(uint32_t mode, uint32_t pull, uint32_t speed) {{
    uint32_t moder_mask = ({pin_mode} << ({pin_num} * 2));
    uint32_t pupdr_mask  = ({pin_pull}  << ({pin_num} * 2));
    uint32_t ospeedr_mask = ({pin_speed} << ({pin_num} * 2));

    GPIO{port}->MODER   = (GPIO{port}->MODER   & ~moder_mask)    | moder_mask;
    GPIO{port}->PUPDR   = (GPIO{port}->PUPDR   & ~pupdr_mask)    | pupdr_mask;
    GPIO{port}->OSPEEDR = (GPIO{port}->OSPEEDR & ~ospeedr_mask)  | ospeedr_mask;
}}
"""

    GPIO_ALTERNATE_INIT = """\
void gpio_init_{pin}_af(uint8_t af_number) {{
    uint32_t moder_mask = (0x2 << ({pin_num} * 2));
    uint32_t afr_mask   = (0xF << ({pin_num} % 8) * 4);

    GPIO{port}->MODER = (GPIO{port}->MODER & ~moder_mask) | moder_mask;
    GPIO{port}->AFR[{pin_num} / 8] = (GPIO{port}->AFR[{pin_num} / 8] & ~afr_mask)
                                     | ((af_number & 0xF) << ({pin_num} % 8) * 4);
}}
"""

    # ─── USART ───────────────────────────────────────────────────────

    USART_INIT = """\
void {peripheral}_init(uint32_t baudrate) {{
    uint16_t brr = SystemCoreClock / baudrate / 16;

    /* Enable clock */
    {clock_enable}

    /* Disable USART during configuration */
    {peripheral}->CR1 = 0;

    /* Set baudrate */
    {peripheral}->BRR = brr;

    /* Configure: 8 data bits, 1 stop bit, no parity */
    {peripheral}->CR1 |= USART_CR1_TE | USART_CR1_RE | USART_CR1_RXNEIE;

    /* Enable USART */
    {peripheral}->CR1 |= USART_CR1_UE;
}}
"""

    USART_WRITE = """\
void {peripheral}_write(uint8_t data) {{
    {peripheral}->DR = data;
    while (!({peripheral}->SR & USART_SR_TXE));
}}
"""

    USART_READ = """\
uint8_t {peripheral}_read(void) {{
    return (uint8_t)({peripheral}->DR & 0xFF);
}}
"""

    USART_WRITE_STRING = """\
void {peripheral}_write_string(const char *str) {{
    while (*str) {{
        {peripheral}_write((uint8_t)*str++);
    }}
}}
"""

    # ─── SPI ────────────────────────────────────────────────────────

    SPI_INIT = """\
void {peripheral}_init(void) {{
    /* Enable clock */
    {clock_enable}

    /* Disable SPI during configuration */
    {peripheral}->CR1 = 0;
    {peripheral}->CR2 = 0;

    /* Master mode, software NSS, MSB first, no CRC */
    {peripheral}->CR1 |= SPI_CR1_MSTR | SPI_CR1_SSM | SPI_CR1_SSI;

    /* Enable SPI */
    {peripheral}->CR1 |= SPI_CR1_SPE;
}}
"""

    SPI_TRANSFER = """\
uint8_t {peripheral}_transfer(uint8_t data) {{
    {peripheral}->DR = data;
    while (!({peripheral}->SR & SPI_SR_RXNE));
    return (uint8_t)({peripheral}->DR & 0xFF);
}}
"""

    SPI_WRITE_READ = """\
void {peripheral}_write_read(uint8_t *tx_buf, uint8_t *rx_buf, uint16_t len) {{
    for (uint16_t i = 0; i < len; i++) {{
        uint8_t rx = {peripheral}_transfer(tx_buf[i]);
        if (rx_buf) rx_buf[i] = rx;
    }}
}}
"""

    # ─── I2C ───────────────────────────────────────────────────────

    I2C_INIT = """\
void {peripheral}_init(void) {{
    /* Enable clock */
    {clock_enable}

    /* Reset I2C */
    {peripheral}->CR1 |= I2C_CR1_SWRST;
    {peripheral}->CR1 &= ~I2C_CR1_SWRST;

    /* Disable while configuring */
    {peripheral}->CR1 &= ~I2C_CR1_PE;
}}
"""

    I2C_WRITE_REG = """\
void {peripheral}_write_reg(uint8_t addr, uint8_t reg, uint8_t data) {{
    /* Wait until not busy */
    while ({peripheral}->SR2 & I2C_SR2_BUSY);

    /* Generate START */
    {peripheral}->CR1 |= I2C_CR1_START;

    /* Send address */
    {peripheral}->DR = (addr << 1) | 0;
    /* Wait for ADDR flag... */

    /* Send register */
    {peripheral}->DR = reg;

    /* Send data */
    {peripheral}->DR = data;

    /* Generate STOP */
    {peripheral}->CR1 |= I2C_CR1_STOP;
}}
"""

    # ─── CAN ────────────────────────────────────────────────────────

    CAN_INIT = """\
void {peripheral}_init(void) {{
    /* Enable clock */
    {clock_enable}

    /* Enter initialization mode */
    {peripheral}->MCR |= CAN_MCR_INRQ;

    /* Configure: normal mode, auto-retransmit, FIFO locked */
    {peripheral}->MCR &= ~(CAN_MCR_DBF | CAN_MCR_TTCM | CAN_MCR_ABOM
                           | CAN_MCR_NART | CAN_MCR_RFLM | CAN_MCR_TXFP);

    /* Exit initialization mode */
    {peripheral}->MCR &= ~CAN_MCR_INRQ;
}}
"""

    CAN_LOOPBACK_INIT = """\
void {peripheral}_loopback_init(void) {{
    /* Enter initialization mode */
    {peripheral}->MCR |= CAN_MCR_INRQ;

    /* Loopback mode: TX outputs fed back to RX */
    {peripheral}->BTR |= CAN_BTR_LBKM | CAN_BTR_SILM;

    /* Exit initialization mode */
    {peripheral}->MCR &= ~CAN_MCR_INRQ;
}}
"""

    # ─── Timer ───────────────────────────────────────────────────────

    TIM_INIT = """\
void {peripheral}_init(uint16_t prescaler, uint16_t period) {{
    /* Enable clock */
    {clock_enable}

    /* Disable timer */
    {peripheral}->CR1 &= ~TIM_CR1_CEN;

    /* Configure */
    {peripheral}->PSC = prescaler;
    {peripheral}->ARR = period;

    /* Generate update to load preload registers */
    {peripheral}->EGR |= TIM_EGR_UG;

    /* Enable timer */
    {peripheral}->CR1 |= TIM_CR1_CEN;
}}
"""

    # ─── Interrupt Handler Stubs ─────────────────────────────────────

    ISR_STUB_TEMPLATE = """\
void {handler_name}(void) {{
    /* {peripheral} IRQ Handler */
    uint32_t status;

    /* Clear interrupt flags and process pending events */
    /* NOTE: Add peripheral-specific handling based on active flags */
}}
"""

    # ─── Clock Enable Macros ─────────────────────────────────────────

    RCC_ENABLE_MACRO = """\
#define {macro_name}(periph) do {{ \\
    RCC->{reg} |= RCC_{reg}_##periph; \\
}} while (0)
"""

    USART_TEMPLATES = {
        "init": USART_INIT,
        "write": USART_WRITE,
        "read": USART_READ,
        "write_string": USART_WRITE_STRING,
    }

    SPI_TEMPLATES = {
        "init": SPI_INIT,
        "transfer": SPI_TRANSFER,
        "write_read": SPI_WRITE_READ,
    }

    @classmethod
    def get_template(cls, peripheral_type: str, template_name: str) -> str:
        """Get a named template for a peripheral type."""
        lookup = {
            "USART": cls.USART_TEMPLATES,
            "SPI": cls.SPI_TEMPLATES,
        }
        templates = lookup.get(peripheral_type.upper(), {})
        return templates.get(template_name, "")
