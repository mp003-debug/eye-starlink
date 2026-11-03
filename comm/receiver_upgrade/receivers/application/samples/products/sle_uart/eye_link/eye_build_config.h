#ifndef BEARPI_EYE_BUILD_CONFIG_H
#define BEARPI_EYE_BUILD_CONFIG_H

/* HiSpark injects the generated mconfig.h with compiler -include. Its output
 * directory is not on the normal header search path in this SDK. */

#if defined(CONFIG_EYE_LINK_NODE_B)
#define EYE_NODE_ID 1
#elif defined(CONFIG_EYE_LINK_NODE_C)
#define EYE_NODE_ID 2
#elif defined(CONFIG_EYE_LINK_NODE_D)
#define EYE_NODE_ID 3
#else
#error Select exactly one eye link receiver identity in Kconfig
#endif

/* Only node A uses this mask; keep the production protocol default. */
#define EYE_REQUIRED_MASK 7

#endif
