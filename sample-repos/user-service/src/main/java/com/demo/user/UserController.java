package com.demo.user;

import org.apache.commons.text.StringEscapeUtils;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class UserController {

    @GetMapping("/health")
    public String health() {
        return "ok";
    }

    @GetMapping("/users/echo")
    public String echo(@RequestParam(defaultValue = "demo") String message) {
        return StringEscapeUtils.escapeHtml4(message);
    }
}
